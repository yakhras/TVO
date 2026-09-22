from odoo import fields, models


class LogisticsContainerLineQtyOverrideWiz(models.TransientModel):
    _name = 'logistics.container.line.qty.override.wiz'
    _description = 'Container Line Quantity Over Agreement — Detail'

    container_line_id = fields.Many2one(
        'logistics.container.line', string='Container Line', readonly=True,
    )
    product_id = fields.Many2one(related='container_line_id.product_id', readonly=True)
    requisition_id = fields.Many2one(related='container_line_id.requisition_id', readonly=True)
    current_qty = fields.Float(string='Entered Quantity', readonly=True)
    remaining_qty = fields.Float(string='Agreement Remaining', readonly=True)
    excess_qty = fields.Float(string='Excess Over Agreement', readonly=True)
    uom_name = fields.Char(string='Unit', readonly=True)
