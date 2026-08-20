from odoo import api, fields, models
from odoo.fields import Command


class LogisticsBillLading(models.Model):
    _name = 'logistics.bill.lading'
    _description = 'Bill of Lading'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'bl_date desc, id desc'
    _rec_name = 'number'
    _rec_names_search = ['name', 'number']
    _sql_constraints = [
        ('number_unique', 'UNIQUE(number)',
         'B/L Number must be unique.'),
    ]

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default='New',
    )
    number = fields.Char(string='B/L Number', tracking=True)
    bl_date = fields.Date(string='B/L Date', tracking=True)
    bl_draft = fields.Boolean(string='B/L Draft', tracking=True)

    forwarder_id = fields.Many2one('res.partner', string='Forwarder', tracking=True)
    shipping_line_id = fields.Many2one('logistics.shipping.line', string='Shipping Line', tracking=True)
    ccl_company_id = fields.Many2one('res.partner', string='CCL Company', tracking=True)
    vessel = fields.Char(string='Vessel', tracking=True)
    incoterm_id = fields.Many2one('account.incoterms', string='Delivery Terms', tracking=True)

    port_of_loading_id = fields.Many2one('logistics.port', string='Port From', tracking=True)
    port_of_discharge_id = fields.Many2one('logistics.port', string='Port To', tracking=True)
    departure_date = fields.Date(string='Departure Date', tracking=True)
    arrival_date = fields.Date(string='Arriving Date', tracking=True)

    docs_draft = fields.Boolean(string='Docs Draft', tracking=True)
    docs_original = fields.Boolean(string='Docs Original', tracking=True)
    bl_original_release = fields.Boolean(string='BL Org./Release', tracking=True)
    ordino = fields.Boolean(string='Ordino', tracking=True)
    custom_declaration = fields.Boolean(string='Custom Declaration', tracking=True)

    requisition_ids = fields.Many2many(
        'purchase.requisition', string='Purchase Agreements',
    )
    container_ids = fields.One2many(
        'logistics.container', 'bill_lading_id', string='Containers',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )

    # --- Computed counts ---
    container_count = fields.Integer(compute='_compute_container_count', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'logistics.bill.lading') or 'New'
        return super().create(vals_list)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.number or rec.name


    @api.depends('container_ids')
    def _compute_container_count(self):
        for rec in self:
            rec.container_count = len(rec.container_ids)

    def action_view_containers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Containers',
            'res_model': 'logistics.container',
            'view_mode': 'list,form',
            'domain': [('bill_lading_id', '=', self.id)],
            'context': {
                'default_bill_lading_id': self.id,
                'default_requisition_ids': [(6, 0, self.requisition_ids.ids)],
            },
        }

    def action_link_existing_container(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'logistics.container.link.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'logistics.view_logistics_container_link_wizard_form').id,
            'target': 'new',
            'context': {
                'default_bill_lading_id': self.id,
            },
        }
