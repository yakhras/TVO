from odoo import api, fields, models


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
