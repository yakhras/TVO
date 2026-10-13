# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero



class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'


    result = fields.Char('Result')
    location_id = fields.Many2one('stock.location', string='Location')  
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    def button_validate(self):
        self._check_can_validate()
        cost_without_adjusment_lines = self.filtered(lambda c: not c.valuation_adjustment_lines)
        if cost_without_adjusment_lines:
            cost_without_adjusment_lines.compute_landed_cost()
        if not self._check_sum():
            raise UserError(_('Cost and adjustments lines do not match. You should maybe recompute the landed costs.'))

        for cost in self:
            cost = cost.with_company(cost.company_id)
            move = self.env['account.move']
            move_vals = {
                'journal_id': cost.account_journal_id.id,
                'date': cost.date,
                'ref': cost.name,
                'line_ids': [],
                'move_type': 'entry',
            }
            valuation_layer_ids = []
            cost_to_add_byproduct = defaultdict(lambda: 0.0)
            cost_to_add_bylot = defaultdict(lambda: defaultdict(float))
            for line in cost.valuation_adjustment_lines.filtered(lambda line: line.move_id):
                remaining_qty = sum(line.move_id._get_stock_valuation_layer_ids().mapped('remaining_qty'))
                linked_layer = line.move_id._get_stock_valuation_layer_ids()

                # Prorate the value at what's still in stock
                move_qty = line.move_id.product_uom._compute_quantity(line.move_id.quantity, line.move_id.product_id.uom_id)
                cost_to_add = (remaining_qty / move_qty) * line.additional_landed_cost
                product = line.move_id.product_id
                if not cost.company_id.currency_id.is_zero(cost_to_add):
                    vals_list = []
                    if line.move_id.product_id.lot_valuated:
                        for lot_id, sml in line.move_id.move_line_ids.grouped('lot_id').items():
                            lot_layer = linked_layer.filtered(lambda l: l.lot_id == lot_id)[:1]
                            value = cost_to_add * sum(sml.mapped('quantity')) / line.move_id.quantity
                            if product.cost_method in ['average', 'fifo']:
                                cost_to_add_bylot[product][lot_id] += value
                            vals_list.append({
                                'value': value,
                                'unit_cost': 0,
                                'quantity': 0,
                                'remaining_qty': 0,
                                'stock_valuation_layer_id': lot_layer.id,
                                'description': cost.name,
                                'stock_move_id': line.move_id.id,
                                'product_id': line.move_id.product_id.id,
                                'stock_landed_cost_id': cost.id,
                                'company_id': cost.company_id.id,
                                'lot_id': lot_id.id,
                            })
                            lot_layer.remaining_value += value
                    else:
                        vals_list.append({
                            'value': cost_to_add,
                            'unit_cost': 0,
                            'quantity': 0,
                            'remaining_qty': 0,
                            'stock_valuation_layer_id': linked_layer[:1].id,
                            'description': cost.name,
                            'stock_move_id': line.move_id.id,
                            'product_id': line.move_id.product_id.id,
                            'stock_landed_cost_id': cost.id,
                            'company_id': cost.company_id.id,
                            'warehouse_id': line.move_id.location_dest_id.warehouse_id.id,
                        })
                        linked_layer[:1].remaining_value += cost_to_add
                    valuation_layer = self.env['stock.valuation.layer'].create(vals_list)
                    valuation_layer_ids += valuation_layer.ids
                # Update the AVCO/FIFO
                product = line.move_id.product_id
                self.warehouse_id = line.move_id.location_dest_id.warehouse_id
                if product.cost_method in ['average', 'fifo']:
                    cost_to_add_byproduct[product] += cost_to_add
                # Products with manual inventory valuation are ignored because they do not need to create journal entries.
                if product.valuation != "real_time":
                    continue
                # `remaining_qty` is negative if the move is out and delivered proudcts that were not
                # in stock.
                qty_out = 0
                if line.move_id._is_in():
                    qty_out = line.move_id.quantity - remaining_qty
                elif line.move_id._is_out():
                    qty_out = line.move_id.quantity
                move_vals['line_ids'] += line._create_accounting_entries(move, qty_out)

            # batch standard price computation avoid recompute quantity_svl at each iteration
            products = self.env['product.product'].browse(p.id for p in cost_to_add_byproduct.keys()).with_company(cost.company_id)
            # Batch search all warehouse costs at once
            warehouse_costs = self.env['product.location.cost'].search([
                ('product_id', 'in', products.ids),
                ('warehouse_id', '=', self.warehouse_id.id)
            ])
            cost_by_product = {wc.product_id.id: wc for wc in warehouse_costs}

            for product in products:
                warehouse_cost = cost_by_product.get(product.id)
                cost_val = warehouse_cost.cost if warehouse_cost else 0.0
                
                # Cache quantity_svl to avoid computing twice
                qty_svl = product.with_context(warehouse_id=self.warehouse_id.id).quantity_svl
                
                if not float_is_zero(qty_svl, precision_rounding=product.uom_id.rounding):
                    cost_val += cost_to_add_byproduct[product] / qty_svl
                    if warehouse_cost:
                        warehouse_cost.cost = cost_val
                        product.with_company(cost.company_id.id).with_context(disable_auto_svl=True).sudo().write({'standard_price': cost_val})
                if product.lot_valuated:
                    for lot, value in cost_to_add_bylot[product].items():
                        if float_is_zero(lot.quantity_svl, precision_rounding=product.uom_id.rounding):
                            continue
                        lot.sudo().with_context(disable_auto_svl=True).standard_price += value / lot.quantity_svl    
                        
            move_vals['stock_valuation_layer_ids'] = [(6, None, valuation_layer_ids)]
            # We will only create the accounting entry when there are defined lines (the lines will be those linked to products of real_time valuation category).
            cost_vals = {'state': 'done'}
            if move_vals.get("line_ids"):
                move = move.create(move_vals)
                cost_vals.update({'account_move_id': move.id})
            cost.write(cost_vals)
            if cost.account_move_id:
                move._post()
            cost.reconcile_landed_cost()
        return True
        
     