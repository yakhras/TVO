# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, fields


class ProductLocationCost(models.Model):
    _name = 'product.location.cost'
    _description = 'Product Location Cost'

    product_id = fields.Many2one('product.product', string='Product', required=True, ondelete='cascade')
    location_id = fields.Many2one('stock.location', string='Location')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)
    cost = fields.Float('Cost', digits='Product Price')
    
    # History tracking
    history_ids = fields.One2many('product.location.cost.history', 'cost_id', string='Cost History')
    last_updated = fields.Datetime('Last Updated', default=fields.Datetime.now)
    last_updated_by = fields.Many2one('res.users', string='Last Updated By', default=lambda self: self.env.user)

    def write(self, vals):
        # Create history record before updating
        if 'cost' in vals:
            for record in self:
                if record.cost != vals['cost']:
                    self.env['product.location.cost.history'].create({
                        'cost_id': record.id,
                        'old_cost': record.cost,
                        'new_cost': vals['cost'],
                        'changed_by': self.env.user.id,
                        'change_date': fields.Datetime.now(),
                        'change_reason': self.env.context,
                    })
            vals['last_updated'] = fields.Datetime.now()
            vals['last_updated_by'] = self.env.user.id
        return super().write(vals)
    
    