# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, fields, api


class ProductLocationCostHistory(models.Model):
    _name = 'product.location.cost.history'
    _description = 'Product Location Cost History'
    _order = 'change_date desc'

    cost_id = fields.Many2one('product.location.cost', string='Cost Record', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='cost_id.product_id', string='Product', store=True)
    location_id = fields.Many2one(related='cost_id.location_id', string='Location')
    warehouse_id = fields.Many2one(related='cost_id.warehouse_id', string='Warehouse', store=True)
    
    old_cost = fields.Float('Previous Cost', digits='Product Price')
    new_cost = fields.Float('New Cost', digits='Product Price')
    cost_difference = fields.Float('Cost Difference', compute='_compute_cost_difference', store=True)
    cost_change_percent = fields.Float('Change %', compute='_compute_cost_difference', store=True)
    
    change_date = fields.Datetime('Change Date', required=True, default=fields.Datetime.now)
    changed_by = fields.Many2one('res.users', string='Changed By', required=True)
    change_reason = fields.Char('Reason')
    
    @api.depends('old_cost', 'new_cost')
    def _compute_cost_difference(self):
        for record in self:
            record.cost_difference = record.new_cost - record.old_cost
            if record.old_cost:
                record.cost_change_percent = ((record.new_cost - record.old_cost) / record.old_cost) * 100
            else:
                record.cost_change_percent = 0.0
                
