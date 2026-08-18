from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LogisticsContainerLine(models.Model):
    _name = 'logistics.container.line'
    _description = 'Container Line'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    # === IDENTITY ===
    internal_ref = fields.Char(
        string='Internal Ref.', required=True, copy=False,
        readonly=True, default='New',
    )
    old_sku = fields.Char(string='Old SKU')

    # === RELATIONS ===
    container_id = fields.Many2one(
        'logistics.container', string='Container', ondelete='cascade',
    )
    product_id = fields.Many2one('product.product', string='Product', tracking=True)
    bill_lading_id = fields.Many2one(
        'logistics.bill.lading', string='Bill of Lading',
        related='container_id.bill_lading_id', store=True,
    )
    requisition_id = fields.Many2one(
        'purchase.requisition', string='Import Deal',
        store=True, tracking=True,
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        related='container_id.purchase_order_id', store=True,
    )
    forwarder_id = fields.Many2one(
        'res.partner', string='Forwarder',
        related='container_id.forwarder_id', store=True,
    )
    port_of_loading_id = fields.Many2one(
        'logistics.port', string='Port From',
        related='container_id.port_of_loading_id', store=True,
    )
    port_of_discharge_id = fields.Many2one(
        'logistics.port', string='Port To',
        related='container_id.port_of_discharge_id', store=True,
    )
    departure_date = fields.Date(
        string='Departure Date',
        related='container_id.departure_date', store=True,
    )
    arrival_date = fields.Date(
        string='Arriving Date',
        related='container_id.arrival_date', store=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        related='container_id.state',
        string='Status',
        store=True,
        readonly=True,
    )

    # === PRODUCT RELATED ===
    product_template = fields.Char(
        string='Product Template', related='product_id.product_tmpl_id.name',
    )
    category_id = fields.Many2one(
        'product.category', string='Category', related='product_id.categ_id',
    )

    # === COMPUTED HELPERS ===
    allowed_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_allowed_product_ids',
        string='Allowed Products',
    )
    allowed_requisition_ids = fields.Many2many(
        'purchase.requisition',
        compute='_compute_allowed_requisition_ids',
        string='Allowed Requisitions',
    )

    # === QUANTITIES & PRICES ===
    product_uom_id = fields.Many2one('uom.uom', string='Unit', tracking=True)
    sku_weight = fields.Float(string='SKU Weight', digits='Stock Weight', tracking=True)
    sku_price = fields.Float(string='SKU Price', digits='Product Price', tracking=True)
    product_qty = fields.Float(
        string='Quantity', digits='Product Unit of Measure', tracking=True,
    )
    total_weight = fields.Float(
        string='Total Weight', compute='_compute_total_weight', store=True,
        digits='Stock Weight',
    )
    mt_price = fields.Monetary(string='MT Price', currency_field='currency_id', tracking=True)
    subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_subtotal', store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
    )

    # === SHIPPING ===
    vendor_id = fields.Many2one(
        'res.partner', string='Supplier',
        related='requisition_id.vendor_id', store=True,
    )
    origin_country_id = fields.Many2one(
        'res.country', string='Origin',
        related='vendor_id.country_id', store=True,
    )
    bl_departure_date = fields.Date(
        string='Departure Date',
        related='bill_lading_id.departure_date', store=True,
    )
    bl_arrival_date = fields.Date(
        string='Sea Arrival Date',
        related='bill_lading_id.arrival_date', store=True,
    )
    pi_date = fields.Date(
        string='PI Date',
        related='requisition_id.pi_date', store=True,
    )
    invoice_no = fields.Char(
        string='Invoice No.',
        related='container_id.invoice_no', store=True,
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        related='container_id.invoice_date', store=True,
    )
    readiness_date = fields.Date(
        string='Readiness Date',
        related='container_id.readiness_date', store=True,
    )
    port_exiting_date = fields.Date(
        string='Port Exiting Date',
        related='container_id.port_exiting_date', store=True,
    )

    # === POST-ARRIVAL ===
    antrepo_arrival_date = fields.Date(
        string='Antrepo Arrival Date',
        related='container_id.antrepo_arrival_date', store=True,
    )
    wh_arriving_date = fields.Date(
        string='WH Arriving Date',
        related='container_id.wh_arriving_date', store=True,
    )
    destination_country_id = fields.Many2one(
        'res.country', string='Destination Country', tracking=True,
    )
    dest_city_id = fields.Many2one(
        'res.country.state', string='Destination City',
        related='container_id.dest_city_id', store=True,
    )
    transit_invoice_no = fields.Char(string='Transit Fatura No.', tracking=True)

    # === SUPPLIER DEPARTURE ===
    available_to_sale_date = fields.Date(string='Available to Sale Date', tracking=True)
    collection_date = fields.Date(string='Collection Date', tracking=True)

    # === MISC ===
    sequence = fields.Integer(string='Sequence', default=10)

    # _sql_constraints = [
    #     ('internal_ref_uniq', 'unique(internal_ref)',
    #      'Internal Reference must be unique.'),
    # ]

    @api.model_create_multi
    def create(self, vals_list):
        combo_counts = {}
        for vals in vals_list:
            if not vals.get('internal_ref') or vals['internal_ref'] == 'New':
                req_ref = ''
                container_num = 'False'
                if vals.get('requisition_id'):
                    req = self.env['purchase.requisition'].browse(vals['requisition_id'])
                    req_ref = req.reference or req.name or ''
                if vals.get('container_id'):
                    container = self.env['logistics.container'].browse(vals['container_id'])
                    container_num = container.container_number or 'False'
                combo_key = (vals.get('container_id'), vals.get('requisition_id'))
                if combo_key not in combo_counts:
                    combo_counts[combo_key] = self.search_count([
                        ('container_id', '=', combo_key[0]),
                        ('requisition_id', '=', combo_key[1]),
                    ])
                combo_counts[combo_key] += 1
                vals['internal_ref'] = f"{container_num}/{req_ref}/{combo_counts[combo_key]:04d}"
            if (
                not vals.get('sku_price')
                and vals.get('requisition_id')
                and vals.get('product_id')
            ):
                req_line = self.env['purchase.requisition.line'].search([
                    ('requisition_id', '=', vals['requisition_id']),
                    ('product_id', '=', vals['product_id']),
                ], limit=1)
                if req_line:
                    vals['sku_price'] = req_line.price_unit
        return super().create(vals_list)

    def _req_line(self):
        """Return the matching requisition line for the current product."""
        if not self.requisition_id or not self.product_id:
            return self.env['purchase.requisition.line'].browse()
        return self.requisition_id.line_ids.filtered(
            lambda l: l.product_id == self.product_id
        )[:1]

    def _remaining_qty(self):
        """Requisition qty minus what's already allocated in other container lines."""
        req_line = self._req_line()
        if not req_line:
            return None
        domain = [
            ('requisition_id', '=', self.requisition_id.id),
            ('product_id', '=', self.product_id.id),
        ]
        if self._origin.id:
            domain.append(('id', '!=', self._origin.id))
        used = sum(self.env['logistics.container.line'].search(domain).mapped('product_qty'))
        return req_line.product_qty - used

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            if self.product_id.weight:
                self.sku_weight = self.product_id.weight
        req_line = self._req_line()
        if req_line:
            self.sku_price = req_line.price_unit

    @api.onchange('requisition_id')
    def _onchange_line_requisition_id(self):
        req_line = self._req_line()
        if req_line:
            self.sku_price = req_line.price_unit

    @api.onchange('container_id')
    def _onchange_container_id(self):
        if not self.container_id:
            self.requisition_id = False
            return
        reqs = self.container_id.requisition_ids
        if self.requisition_id not in reqs:
            self.requisition_id = reqs[:1] if len(reqs) == 1 else False

    ## This method is dead, because we made the field readonly. Keeping it here in case we want to make it editable again in the future.
    @api.onchange('sku_price')
    def _onchange_sku_price(self):
        req_line = self._req_line()
        if not req_line or not self.sku_price:
            return
        if self.sku_price != req_line.price_unit:
            return {
                'warning': {
                    'title': 'Price Differs from Deal',
                    'message': (
                        f'Entered price {self.sku_price} differs from the deal price '
                        f'{req_line.price_unit} for "{self.product_id.display_name}".'
                    ),
                }
            }

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        remaining = self._remaining_qty()
        if remaining is None:
            return
        if self.product_qty > remaining:
            req_line = self._req_line()
            return {
                'warning': {
                    'title': 'Quantity Exceeds Remaining',
                    'message': (
                        f'Entered quantity {self.product_qty} exceeds the remaining '
                        f'{remaining} {req_line.product_uom_id.name} for '
                        f'"{self.product_id.display_name}" in this deal.'
                    ),
                }
            }

    @api.constrains('product_qty', 'requisition_id', 'product_id')
    def _check_product_qty(self):
        for line in self:
            if not line.requisition_id or not line.product_id:
                continue
            req_line = line.requisition_id.line_ids.filtered(
                lambda l: l.product_id == line.product_id
            )[:1]
            if not req_line:
                continue
            domain = [
                ('requisition_id', '=', line.requisition_id.id),
                ('product_id', '=', line.product_id.id),
                ('id', '!=', line.id),
            ]
            used = sum(
                self.env['logistics.container.line'].search(domain).mapped('product_qty')
            )
            remaining = req_line.product_qty - used
            if line.product_qty > remaining:
                raise ValidationError(
                    f'Quantity {line.product_qty:.2f} for '
                    f'"{line.product_id.display_name}" exceeds the remaining '
                    f'{remaining:.2f} {req_line.product_uom_id.name} '
                    f'in deal "{line.requisition_id.name}".'
                )

    @api.depends(
        'requisition_id',
        'requisition_id.line_ids.product_id',
        'requisition_id.line_ids.product_qty',
    )
    def _compute_allowed_product_ids(self):
        ContainerLine = self.env['logistics.container.line']
        for line in self:
            if not line.requisition_id:
                line.allowed_product_ids = self.env['product.product']
                continue

            allowed = self.env['product.product']
            for req_line in line.requisition_id.line_ids:
                domain = [
                    ('requisition_id', '=', line.requisition_id.id),
                    ('product_id', '=', req_line.product_id.id),
                ]
                if line._origin.id:
                    domain.append(('id', '!=', line._origin.id))
                used = sum(ContainerLine.search(domain).mapped('product_qty'))
                if req_line.product_qty - used > 0:
                    allowed |= req_line.product_id

            line.allowed_product_ids = allowed

    @api.depends('container_id', 'container_id.requisition_ids')
    def _compute_allowed_requisition_ids(self):
        for line in self:
            line.allowed_requisition_ids = line.container_id.requisition_ids

    @api.depends('sku_weight', 'product_qty')
    def _compute_total_weight(self):
        for line in self:
            line.total_weight = line.sku_weight * line.product_qty

    @api.depends('sku_price', 'product_qty')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.sku_price * line.product_qty

    def action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
