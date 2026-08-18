from odoo import fields, models


class LogisticsContainerLinkWizard(models.TransientModel):
    _name = 'logistics.container.link.wizard'
    _description = 'Link Existing Containers to Bill of Lading'

    bill_lading_id = fields.Many2one(
        'logistics.bill.lading', string='Bill of Lading',
        required=True, readonly=True,
    )
    container_ids = fields.Many2many(
        'logistics.container', string='Containers',
        domain=[('bill_lading_id', '=', False)],
    )

    def action_link(self):
        self.ensure_one()
        self.container_ids.write({'bill_lading_id': self.bill_lading_id.id})
        return {'type': 'ir.actions.act_window_close'}
