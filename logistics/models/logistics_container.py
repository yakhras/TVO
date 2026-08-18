import logging

from odoo import api, fields, models
from odoo.fields import Command

_logger = logging.getLogger(__name__)


class LogisticsContainer(models.Model):
    _name = 'logistics.container'
    _description = 'Shipping Container'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_names_search = ['name', 'container_number']
    _sql_constraints = [
        ('container_number_unique', 'UNIQUE(container_number)',
         'Container No. must be unique.'),
    ]

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default='New',
    )
    container_number = fields.Char(string='Container No.', tracking=True)
    container_type = fields.Selection(
        selection=[
            ('20', '20ft'),
            ('40', '40ft'),
            ('truck', 'Truck'),
        ],
        string='Container Type', tracking=True,
    )

    bill_lading_id = fields.Many2one('logistics.bill.lading', string='Bill of Lading', tracking=True)
    requisition_ids = fields.Many2many(
        'purchase.requisition',
        'logistics_container_requisition_rel',
        'container_id', 'requisition_id',
        string='Purchase Agreements', tracking=True,
    )
    purchase_order_id = fields.Many2one(
        'purchase.order', string='Purchase Order', tracking=True,
    )

    forwarder_id = fields.Many2one(
        'res.partner', string='Forwarder',
        related='bill_lading_id.forwarder_id', store=True,
    )
    port_of_loading_id = fields.Many2one(
        'logistics.port', string='Port From',
        related='bill_lading_id.port_of_loading_id', store=True,
    )
    port_of_discharge_id = fields.Many2one(
        'logistics.port', string='Port To',
        related='bill_lading_id.port_of_discharge_id', store=True,
    )
    departure_date = fields.Date(
        string='Departure Date',
        related='bill_lading_id.departure_date', store=True,
    )
    arrival_date = fields.Date(
        string='Arriving Date',
        related='bill_lading_id.arrival_date', store=True,
    )
    invoice_no = fields.Char(string='Invoice No.', tracking=True)
    invoice_date = fields.Date(string='Invoice Date', tracking=True)
    wh_arriving_date = fields.Date(string='WH Arriving Date', tracking=True)
    readiness_date = fields.Date(string='Readiness Date', tracking=True)
    port_exiting_date = fields.Date(string='Port Exiting Date', tracking=True)
    antrepo_arrival_date = fields.Date(string='Antrepo Arrival Date', tracking=True)
    declaration_type_id = fields.Many2one(
        'logistics.declaration.type', string='Declaration Type', tracking=True,
    )
    destination_country_id = fields.Many2one(
        'res.country', string='Destination Country', tracking=True,
    )
    dest_city_id = fields.Many2one(
        'res.country.state', string='Destination City', tracking=True,
    )

    ship_fee_amount = fields.Monetary(
        string='Shipping Fee', currency_field='ship_fee_currency_id', tracking=True,
    )
    ship_fee_currency_id = fields.Many2one(
        'res.currency', string='Ship Fee Currency',
        default=lambda self: self.env.company.currency_id,
    )
    extra_fee_payment_term_id = fields.Many2one(
        'account.payment.term', string='Extra Fee Payment Terms', tracking=True,
    )

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    amount_subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_amount_totals',
        store=True, currency_field='currency_id',
    )
    amount_total = fields.Monetary(
        string='Total', compute='_compute_amount_totals',
        store=True, currency_field='currency_id',
    )

    container_line_ids = fields.One2many(
        'logistics.container.line', 'container_id', string='Container Lines',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )

    state = fields.Selection(
        selection=[
            ('purchase', 'Purchasing'),
            ('oversea', 'Oversea'),
            ('at_port', 'At Port'),
            ('arrived', 'Arrived'),
            ('antrepo', 'Antrepo'),
        ],
        string='Status', default='purchase', required=True,
        copy=False, tracking=True,
    )

    # --- Computed counts ---
    line_count = fields.Integer(compute='_compute_line_count')
    has_remaining_allocation = fields.Boolean(
        compute='_compute_has_remaining_allocation',
        store=True,
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'requisition_ids' in fields_list and not defaults.get('requisition_ids'):
            bill_lading_id = defaults.get('bill_lading_id') or self.env.context.get('default_bill_lading_id')
            if bill_lading_id:
                bill_lading = self.env['logistics.bill.lading'].browse(bill_lading_id)
                if bill_lading.requisition_ids:
                    defaults['requisition_ids'] = [Command.set(bill_lading.requisition_ids.ids)]
        return defaults

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.container_number or rec.name

    @api.onchange('requisition_ids')
    def _onchange_requisition_ids(self):
        # self.container_line_ids is empty in onchange for saved containers —
        # the client only sends dirty fields; untouched One2many lines are absent.
        # Use _origin (saved DB record) as the reliable source.
        origin_lines = (
            self.env['logistics.container.line'].search(
                [('container_id', '=', self._origin.id)]
            )
            if self._origin.id
            else self.env['logistics.container.line']
        )
        covered_pairs = {
            (line.requisition_id.id, line.product_id.id)
            for line in (origin_lines | self.container_line_ids)
            if line.requisition_id and line.product_id
        }
        _logger.info(
            "[container %s] onchange_requisition_ids: origin_id=%s "
            "virtual_lines=%d origin_lines=%d covered_pairs=%s reqs=%s",
            self.name or 'NEW', self._origin.id,
            len(self.container_line_ids), len(origin_lines),
            covered_pairs, self.requisition_ids.mapped('name'),
        )

        new_lines = self.env['logistics.container.line']
        for req in self.requisition_ids:
            # In onchange, Many2many records are virtual copies; req.id = NewId.
            # Use _origin.id to get the actual integer DB ID.
            req_id = req._origin.id
            if not req_id or not req.line_ids:
                continue
            domain = [('requisition_id', '=', req_id)]
            if self._origin.id:
                domain.append(('container_id', '!=', self._origin.id))
            other_lines = self.env['logistics.container.line'].search(domain)
            used_qty = {}
            for ol in other_lines:
                pid = ol.product_id.id
                used_qty[pid] = used_qty.get(pid, 0.0) + ol.product_qty

            for line in req.line_ids:
                pid = line.product_id.id
                if (req_id, pid) in covered_pairs:
                    _logger.info(
                        "[container %s] req=%s product=%s COVERED skip",
                        self.name or 'NEW', req.name, line.product_id.name,
                    )
                    continue
                remaining = line.product_qty - used_qty.get(pid, 0.0)
                if remaining <= 0:
                    _logger.info(
                        "[container %s] req=%s product=%s remaining=%.2f skip",
                        self.name or 'NEW', req.name, line.product_id.name, remaining,
                    )
                    continue
                _logger.info(
                    "[container %s] req=%s product=%s ADDING qty=%.2f",
                    self.name or 'NEW', req.name, line.product_id.name, remaining,
                )
                new_lines |= self.env['logistics.container.line'].new({
                    'product_id': pid,
                    'product_qty': remaining,
                    'product_uom_id': line.product_uom_id.id,
                    'sku_price': line.price_unit,
                    'requisition_id': req_id,
                    'sku_weight': line.product_id.weight or 0.0,
                })

        if new_lines:
            self.container_line_ids = self.container_line_ids | new_lines

    @api.onchange('container_line_ids')
    def _onchange_container_line_ids(self):
        if not self.requisition_ids:
            return

        req_product_ids = set(
            line.product_id.id
            for req in self.requisition_ids
            for line in req.line_ids
            if line.product_id
        )

        for line in self.container_line_ids:
            if line.product_id and line.product_id.id not in req_product_ids:
                return {
                    'warning': {
                        'title': 'Product Not in Deal',
                        'message': (
                            f'"{line.product_id.display_name}" is not listed in any '
                            f'selected deal. It will be saved as-is.'
                        ),
                    }
                }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'logistics.container') or 'New'
        records = super().create(vals_list)
        bls = records.mapped('bill_lading_id').filtered(bool)
        records._sync_bl_requisitions(bls)
        return records

    def write(self, vals):
        # Identify containers going from no number → a number (for ref sync)
        if vals.get('container_number'):
            no_number_before = self.filtered(lambda c: not c.container_number)
        else:
            no_number_before = self.env['logistics.container']

        needs_sync = 'bill_lading_id' in vals or 'requisition_ids' in vals
        old_bls = {
            container.id: container.bill_lading_id
            for container in self
        } if needs_sync else {}

        result = super().write(vals)

        # Sync internal_ref: replace '/False/' with the real container number
        for container in no_number_before:
            lines_to_fix = container.container_line_ids.filtered(
                lambda l: l.internal_ref and '/False/' in l.internal_ref
            )
            for line in lines_to_fix:
                line.internal_ref = line.internal_ref.replace(
                    '/False/', f'/{container.container_number}/', 1
                )

        if needs_sync and not self.env.context.get('from_bl_req_sync'):
            bls = self.env['logistics.bill.lading']
            for container in self:
                if container.bill_lading_id:
                    bls |= container.bill_lading_id
                old_bl = old_bls.get(container.id)
                if old_bl and old_bl != container.bill_lading_id:
                    bls |= old_bl
            self._sync_bl_requisitions(bls)

        return result

    def _sync_bl_requisitions(self, bls):
        for bl in bls:
            bl.requisition_ids = bl.container_ids.requisition_ids
            for req in bl.requisition_ids:
                if bl not in req.bill_lading_ids:
                    req.bill_lading_ids = [Command.link(bl.id)]

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        default['container_line_ids'] = [(5,)]
        new_container = super().copy(default)

        ContainerLine = self.env['logistics.container.line']
        new_lines = []
        for req in new_container.requisition_ids:
            if not req.line_ids:
                continue
            other_lines = ContainerLine.search([
                ('requisition_id', '=', req.id),
                ('container_id', '!=', new_container.id),
            ])
            used_qty = {}
            for ol in other_lines:
                pid = ol.product_id.id
                used_qty[pid] = used_qty.get(pid, 0.0) + ol.product_qty

            for req_line in req.line_ids:
                pid = req_line.product_id.id
                remaining = req_line.product_qty - used_qty.get(pid, 0.0)
                if remaining <= 0:
                    continue
                new_lines.append((0, 0, {
                    'product_id': pid,
                    'product_qty': remaining,
                    'product_uom_id': req_line.product_uom_id.id,
                    'sku_price': req_line.price_unit,
                    'requisition_id': req.id,
                    'sku_weight': req_line.product_id.weight or 0.0,
                }))

        if new_lines:
            new_container.write({'container_line_ids': new_lines})
        return new_container


    @api.depends(
        'container_line_ids.subtotal',
        'ship_fee_amount',
    )
    def _compute_amount_totals(self):
        for rec in self:
            rec.amount_subtotal = sum(rec.container_line_ids.mapped('subtotal'))
            rec.amount_total = (
                rec.amount_subtotal
                + (rec.ship_fee_amount or 0.0)
            )

    @api.depends('container_line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.container_line_ids)

    @api.depends('requisition_ids', 'requisition_ids.remaining_qty')
    def _compute_has_remaining_allocation(self):
        for container in self:
            container.has_remaining_allocation = any(
                req.remaining_qty > 0 for req in container.requisition_ids
            )

    def action_view_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Container Lines',
            'res_model': 'logistics.container.line',
            'view_mode': 'list,form',
            'domain': [('container_id', '=', self.id)],
            'context': {'default_container_id': self.id},
        }
