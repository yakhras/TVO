import logging

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PoToSoWizard(models.TransientModel):
    _name = 'po.to.so.wizard'
    _description = 'Convert Purchase Orders to Sale Order'

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Purchase Orders',
        domain=[('state', 'in', ('purchase', 'done'))],
        help='Only confirmed ("purchase") or locked ("done") purchase orders can be converted.',
    )

    product_selection_mode = fields.Selection(
        selection=[('all', 'All Products'), ('some', 'Selected Products')],
        string='Products',
        default='all',
        required=True,
    )

    qty_mode = fields.Selection(
        selection=[
            ('same', 'Same as Source'),
            ('fixed', 'Adjust by Fixed Amount'),
            ('manual', 'Manual per Line'),
        ],
        string='Quantity',
        default='same',
        required=True,
    )
    qty_fixed_delta = fields.Float(string='Quantity +/-')

    price_mode = fields.Selection(
        selection=[
            ('same', 'Same as Source'),
            ('fixed', 'Adjust by Fixed Amount'),
            ('percentage', 'Adjust by Percentage'),
            ('manual', 'Manual per Line'),
        ],
        string='Price',
        default='same',
        required=True,
    )
    price_fixed_delta = fields.Monetary(string='Price +/-', currency_field='currency_id')
    price_percentage_delta = fields.Float(string='Price +/- %')

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        required=True,
        default=lambda self: self.env.user._get_default_warehouse_id(),
    )
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='pricelist_id.currency_id',
        readonly=True,
    )
    tax_ids = fields.Many2many(
        'account.tax',
        string='Tax',
        domain=[('type_tax_use', '=', 'sale')],
        help='Applied to every converted line. Leave empty to keep each '
             "product's own default sale tax.",
    )

    line_ids = fields.One2many('po.to.so.wizard.line', 'wizard_id', string='Lines')

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.pricelist_id = self.partner_id.property_product_pricelist

    @api.onchange('purchase_order_ids')
    def _onchange_purchase_order_ids(self):
        lines = []
        for order in self.purchase_order_ids:
            for po_line in order.order_line:
                if po_line.display_type:
                    continue
                _logger.info(
                    'po_to_so onchange building line: po_line=%s product=%s product_qty=%s price_unit=%s',
                    po_line.id, po_line.product_id.display_name, po_line.product_qty, po_line.price_unit,
                )
                lines.append(Command.create({
                    'source_po_line_id': po_line.id,
                    'product_id': po_line.product_id.id,
                    'product_uom': po_line.product_uom.id,
                    'source_qty': po_line.product_qty,
                    'source_price_unit': po_line.price_unit,
                    'product_uom_qty': po_line.product_qty,
                    'price_unit': po_line.price_unit,
                }))
        self.line_ids = lines

    def action_apply_bulk_settings(self):
        """Re-apply the current quantity/price bulk mode to every line.

        Lines are only touched here, on explicit user request, so a line the
        user hand-edited afterwards is never silently overwritten except when
        this button is clicked again.
        """
        self.ensure_one()
        _logger.info(
            'po_to_so apply_bulk_settings: wizard=%s qty_mode=%s qty_fixed_delta=%s '
            'price_mode=%s price_fixed_delta=%s price_percentage_delta=%s lines=%s',
            self.id, self.qty_mode, self.qty_fixed_delta,
            self.price_mode, self.price_fixed_delta, self.price_percentage_delta,
            self.line_ids.ids,
        )
        for line in self.line_ids:
            _logger.info(
                'po_to_so line=%s product=%s BEFORE source_qty=%s product_uom_qty=%s '
                'source_price_unit=%s price_unit=%s',
                line.id, line.product_id.display_name, line.source_qty, line.product_uom_qty,
                line.source_price_unit, line.price_unit,
            )
            if self.qty_mode == 'same':
                line.product_uom_qty = line.source_qty
            elif self.qty_mode == 'fixed':
                new_qty = line.source_qty + self.qty_fixed_delta
                if new_qty <= 0:
                    raise UserError(_(
                        'Adjusting the quantity of "%(product)s" by %(delta)s would '
                        'result in a quantity of zero or less.',
                        product=line.product_id.display_name,
                        delta=self.qty_fixed_delta,
                    ))
                line.product_uom_qty = new_qty

            if self.price_mode == 'same':
                line.price_unit = line.source_price_unit
            elif self.price_mode == 'fixed':
                line.price_unit = line.source_price_unit + self.price_fixed_delta
            elif self.price_mode == 'percentage':
                line.price_unit = line.source_price_unit * (1 + self.price_percentage_delta / 100.0)
            _logger.info(
                'po_to_so line=%s AFTER product_uom_qty=%s price_unit=%s',
                line.id, line.product_uom_qty, line.price_unit,
            )

        # Returning nothing here would make the Odoo web client close this
        # wizard dialog instead of just refreshing it, since it was opened
        # with target='new'. Re-open the same record explicitly so the
        # dialog stays open with the recomputed line values visible.
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'po.to.so.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('sale_extension_po_to_so.view_po_to_so_wizard_form').id,
            'target': 'new',
        }

    def _get_relevant_lines(self):
        self.ensure_one()
        if self.product_selection_mode == 'all':
            return self.line_ids
        return self.line_ids.filtered('include')

    def action_confirm(self):
        self.ensure_one()

        relevant_lines = self._get_relevant_lines()

        errors = []
        if not self.purchase_order_ids:
            errors.append(_('Please select at least one purchase order.'))
        if not relevant_lines:
            errors.append(_('Please include at least one product line.'))
        if any(line.product_uom_qty <= 0 for line in relevant_lines):
            errors.append(_('All included lines must have a quantity greater than zero.'))
        if not self.partner_id:
            errors.append(_('Please select a customer.'))
        if not self.warehouse_id:
            errors.append(_('Please select a warehouse.'))
        if not self.pricelist_id:
            errors.append(_('Please select a pricelist (the chosen customer may have no default one).'))
        if errors:
            raise UserError('\n'.join(errors))

        order_line_vals = []
        for line in relevant_lines:
            line_vals = {
                'product_id': line.product_id.id,
                'name': line.source_po_line_id.name,
                'product_uom_qty': line.product_uom_qty,
                'product_uom': line.product_uom.id,
                'price_unit': line.price_unit,
            }
            # Only override the tax when the user picked one; otherwise leave
            # tax_id out of the vals so Odoo derives it from the product as usual.
            if self.tax_ids:
                line_vals['tax_id'] = [Command.set(self.tax_ids.ids)]
            order_line_vals.append(Command.create(line_vals))

        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'warehouse_id': self.warehouse_id.id,
            'pricelist_id': self.pricelist_id.id,
            'user_id': self.env.user.id,
            'company_id': self.env.company.id,
            'origin': ', '.join(self.purchase_order_ids.mapped('name')),
            'order_line': order_line_vals,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'view_id': self.env.ref('sale.view_order_form').id,
            'target': 'current',
        }


class PoToSoWizardLine(models.TransientModel):
    _name = 'po.to.so.wizard.line'
    _description = 'Convert Purchase Orders to Sale Order - Line'

    wizard_id = fields.Many2one('po.to.so.wizard', required=True, ondelete='cascade')
    include = fields.Boolean(string='Include', default=True)
    source_po_line_id = fields.Many2one('purchase.order.line', string='Source Line', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    source_qty = fields.Float(string='Source Quantity', readonly=True)
    source_price_unit = fields.Float(string='Source Price', readonly=True)
    product_uom_qty = fields.Float(string='Quantity')
    price_unit = fields.Float(string='Price')
    currency_id = fields.Many2one(related='wizard_id.currency_id', store=True, readonly=True)
    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id',
        help='Untaxed amount (quantity x price).',
    )
    price_tax = fields.Monetary(
        string='Tax',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id',
        help="Amount of the wizard's selected tax on this line.",
    )
    price_total = fields.Monetary(
        string='Total',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id',
        help='Subtotal plus tax.',
    )

    @api.depends('product_uom_qty', 'price_unit', 'wizard_id.tax_ids')
    def _compute_amount(self):
        for line in self:
            taxes = line.wizard_id.tax_ids.compute_all(
                line.price_unit,
                line.currency_id,
                line.product_uom_qty,
                product=line.product_id,
                partner=line.wizard_id.partner_id,
            )
            line.price_tax = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
            line.price_total = taxes['total_included']
            line.price_subtotal = taxes['total_excluded']
