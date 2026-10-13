# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools.float_utils import float_is_zero


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    unit_value = fields.Monetary('Unit Value')

    @api.depends('company_id', 'location_id', 'owner_id', 'product_id', 'quantity')
    def _compute_value(self):
        """ For standard and AVCO valuation, compute the current accounting
        valuation of the quants by multiplying the quantity by
        the standard price. Instead for FIFO, use the quantity times the
        average cost (valuation layers are not manage by location so the
        average cost is the same for all location and the valuation field is
        a estimation more than a real value).
        """
        for quant in self:
            quant.currency_id = quant.company_id.currency_id
            # If the user didn't enter a location yet while enconding a quant.
            if not quant.location_id:
                quant.value = 0
                return

            if not quant.location_id._should_be_valued() or\
                    (quant.owner_id and quant.owner_id != quant.company_id.partner_id):
                quant.value = 0
                continue
            if quant.product_id.cost_method == 'fifo':
                quantity = quant.product_id.with_context(warehouse_id = quant.location_id.warehouse_id.id).with_company(quant.company_id).quantity_svl
                if float_is_zero(quantity, precision_rounding=quant.product_id.uom_id.rounding):
                    quant.value = 0.0
                    continue
                average_cost = quant.product_id.with_context(warehouse_id = quant.location_id.warehouse_id.id).with_company(quant.company_id).value_svl / quantity
                quant.value = quant.quantity * average_cost
                quant.unit_value = average_cost
            else:
                if quant.location_id and quant.product_id:
                    location_cost = self.env['product.location.cost'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('warehouse_id', '=', quant.location_id.warehouse_id.id)
                    ], order='id desc', limit=1)  # Get the most recent record

                    cost_value = location_cost.cost if location_cost else 0.0
                quant.value = quant.quantity * cost_value
                quant.unit_value = cost_value
            
            