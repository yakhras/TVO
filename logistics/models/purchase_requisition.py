from odoo import api, fields, models


class PurchaseRequisitionLine(models.Model):
    _inherit = 'purchase.requisition.line'

    description_picking = fields.Text(
        string='Description on Picking',
        compute='_compute_description_picking', store=True, readonly=True,
    )

    # --- Pivot analysis ---
    categ_id = fields.Many2one(
        'product.category', string='Product Category',
        related='product_id.categ_id', store=True,
    )
    po_qty_ordered = fields.Float(
        string='Qty Ordered', digits='Product Unit of Measure',
        compute='_compute_po_quantities', store=True,
    )
    po_qty_received = fields.Float(
        string='Qty Received', digits='Product Unit of Measure',
        compute='_compute_po_quantities', store=True,
    )
    po_qty_billed = fields.Float(
        string='Qty Billed', digits='Product Unit of Measure',
        compute='_compute_po_quantities', store=True,
    )
    qty_to_order = fields.Float(
        string='Remaining to Order', digits='Product Unit of Measure',
        compute='_compute_po_quantities', store=True,
    )
    qty_to_receive = fields.Float(
        string='Remaining to Receive', digits='Product Unit of Measure',
        compute='_compute_po_quantities', store=True,
    )
    qty_to_bill = fields.Float(
        string='Remaining to Bill', digits='Product Unit of Measure',
        compute='_compute_po_quantities', store=True,
    )
    total_weight = fields.Float(
        string='Total Weight', digits='Stock Weight',
        compute='_compute_total_weight', store=True,
    )
    # Subtotal of the lines that have a weight; used to weight Average Kg Price.
    weighted_subtotal = fields.Monetary(
        compute='_compute_avg_prices', store=True,
    )
    avg_price_unit = fields.Float(
        string='Average Unit Price', digits='Product Price',
        compute='_compute_avg_prices', store=True, aggregator='avg',
    )
    avg_kg_price = fields.Float(
        string='Average Kg Price', digits='Product Price',
        compute='_compute_avg_prices', store=True, aggregator='avg',
    )

    @api.depends('product_id.product_tmpl_id.description_picking')
    def _compute_description_picking(self):
        for line in self:
            line.description_picking = line.product_id.description_picking

    @api.depends(
        'product_id', 'product_uom_id', 'product_qty',
        'requisition_id.purchase_ids.state',
        'requisition_id.purchase_ids.order_line.product_qty',
        'requisition_id.purchase_ids.order_line.qty_received',
        'requisition_id.purchase_ids.order_line.qty_invoiced',
    )
    def _compute_po_quantities(self):
        # Same matching as core qty_ordered: confirmed POs of the agreement,
        # same product, quantities counted once, on the first line of that product.
        for line in self:
            ordered = received = billed = 0.0
            first = line.requisition_id.line_ids.filtered(lambda l: l.product_id == line.product_id)[:1]
            if first == line:
                pos = line.requisition_id.purchase_ids.filtered(lambda po: po.state in ('purchase', 'done'))
                for po_line in pos.order_line.filtered(lambda l: l.product_id == line.product_id):
                    to_uom = line.product_uom_id or po_line.product_uom
                    convert = po_line.product_uom._compute_quantity
                    ordered += convert(po_line.product_qty, to_uom)
                    received += convert(po_line.qty_received, to_uom)
                    billed += convert(po_line.qty_invoiced, to_uom)
            line.po_qty_ordered = ordered
            line.po_qty_received = received
            line.po_qty_billed = billed
            line.qty_to_order = line.product_qty - ordered
            line.qty_to_receive = ordered - received
            line.qty_to_bill = ordered - billed

    @api.depends('product_id.weight', 'product_qty', 'product_uom_id')
    def _compute_total_weight(self):
        weight_uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        for line in self:
            uom = line.product_uom_id
            if uom and uom.category_id == weight_uom.category_id:
                line.total_weight = uom._compute_quantity(line.product_qty, weight_uom)
            elif line.product_id and uom:
                qty = uom._compute_quantity(line.product_qty, line.product_id.uom_id)
                line.total_weight = qty * line.product_id.weight
            else:
                line.total_weight = 0.0

    @api.depends('price_unit', 'price_subtotal', 'total_weight')
    def _compute_avg_prices(self):
        for line in self:
            line.avg_price_unit = line.price_unit
            line.weighted_subtotal = line.price_subtotal if line.total_weight else 0.0
            line.avg_kg_price = line.price_subtotal / line.total_weight if line.total_weight else 0.0

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        # Replace the plain average of the averages with a quantity/weight-weighted one.
        names = {f.split(':')[0] for f in fields}
        want_unit = 'avg_price_unit' in names
        want_kg = 'avg_kg_price' in names
        if not (want_unit or want_kg):
            return super().read_group(domain, fields, groupby, offset, limit, orderby, lazy)
        extra = ['price_subtotal:sum', 'product_qty:sum', 'weighted_subtotal:sum', 'total_weight:sum']
        rows = super().read_group(domain, list(fields) + extra, groupby, offset, limit, orderby, lazy)
        for row in rows:
            if want_unit:
                qty = row.get('product_qty') or 0.0
                row['avg_price_unit'] = (row.get('price_subtotal') or 0.0) / qty if qty else 0.0
            if want_kg:
                weight = row.get('total_weight') or 0.0
                row['avg_kg_price'] = (row.get('weighted_subtotal') or 0.0) / weight if weight else 0.0
        return rows


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'
    _rec_names_search = ['name', 'reference']

    # --- New fields ---
    pi_date = fields.Date(string='PI Date')

    # --- Related ---
    origin_country_id = fields.Many2one(
        'res.country', string='Origin',
        related='vendor_id.country_id', store=True,
    )

    description_picking = fields.Text(
        string='Description on Picking',
        compute='_compute_description_picking', store=True, readonly=True,
        help='Distinct "Description on Picking" values of the agreement products.',
    )

    # --- Relational ---
    container_ids = fields.Many2many(
        'logistics.container',
        'logistics_container_requisition_rel',
        'requisition_id', 'container_id',
        string='Containers',
    )
    bill_lading_ids = fields.Many2many(
        'logistics.bill.lading', string='Bills of Lading',
    )

    # --- Computed counts ---
    container_count = fields.Integer(compute='_compute_container_count')
    bill_lading_count = fields.Integer(compute='_compute_bill_lading_count')
    container_line_count = fields.Integer(compute='_compute_container_line_count')

    # --- Logistics state ---
    logistics_state = fields.Selection(
        selection=[
            ('purchasing', 'Purchasing'),
            ('oversea', 'Oversea'),
            ('at_port', 'At Port'),
            ('arrived', 'Arrived'),
            ('completed', 'Completed'),
        ],
        string='Logistics Status', compute='_compute_logistics_state', store=True,
    )

    # --- Blanket order tracking ---
    total_shipped_qty = fields.Float(
        string='Total Shipped Qty', compute='_compute_shipped_remaining', store=True,
    )
    remaining_qty = fields.Float(
        string='Remaining Qty', compute='_compute_shipped_remaining', store=True,
    )

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.reference or rec.name


    @api.depends('line_ids.description_picking')
    def _compute_description_picking(self):
        for rec in self:
            descriptions = []
            for desc in rec.line_ids.mapped('description_picking'):
                if desc and desc not in descriptions:
                    descriptions.append(desc)
            rec.description_picking = ', '.join(descriptions) or False

    @api.depends('container_ids')
    def _compute_container_count(self):
        for rec in self:
            rec.container_count = len(rec.container_ids)

    @api.depends('bill_lading_ids')
    def _compute_bill_lading_count(self):
        for rec in self:
            rec.bill_lading_count = len(rec.bill_lading_ids)

    @api.depends('container_ids.container_line_ids')
    def _compute_container_line_count(self):
        for rec in self:
            rec.container_line_count = sum(
                1
                for c in rec.container_ids
                for l in c.container_line_ids
                if l.requisition_id.id == rec.id
            )

    @api.depends('container_ids.state')
    def _compute_logistics_state(self):
        for rec in self:
            containers = rec.container_ids
            if not containers:
                rec.logistics_state = 'purchasing'
            elif all(c.state == 'unloaded' for c in containers):
                rec.logistics_state = 'completed'
            elif any(c.state in ('arrived', 'antrepo', 'released', 'unloaded') for c in containers):
                rec.logistics_state = 'arrived'
            else:
                rec.logistics_state = 'purchasing'

    @api.depends(
        'container_ids.container_line_ids.product_qty',
        'line_ids.product_qty',
    )
    def _compute_shipped_remaining(self):
        for rec in self:
            shipped = sum(
                line.product_qty
                for container in rec.container_ids
                for line in container.container_line_ids
                if line.requisition_id.id == rec.id
            )
            ordered = sum(rec.line_ids.mapped('product_qty'))
            rec.total_shipped_qty = shipped
            rec.remaining_qty = ordered - shipped

    def action_view_containers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Containers',
            'res_model': 'logistics.container',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.container_ids.ids)],
            'context': {'default_requisition_ids': [(4, self.id)]},
        }

    def action_view_bill_ladings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills of Lading',
            'res_model': 'logistics.bill.lading',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.bill_lading_ids.ids)],
            'context': {'default_requisition_ids': [(4, self.id)]},
        }

    def action_view_container_lines(self):
        self.ensure_one()
        line_ids = self.container_ids.container_line_ids.ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Container Lines',
            'res_model': 'logistics.container.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', line_ids)],
        }
