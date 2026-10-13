# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.tools import float_is_zero, OrderedSet, float_compare



class StockMove(models.Model):
    _inherit = "stock.move"

    result = fields.Text('Result')




    def product_price_update_before_done(self, forced_qty=None):
        tmpl_dict = defaultdict(lambda: 0.0)
        lot_tmpl_dict = defaultdict(lambda: 0.0)
        # adapt standard price on incomming moves if the product cost_method is 'average'
        std_price_update = {}
        std_price_update_lot = {}

        def update_product_location_cost(product_id, warehouse_id, cost):
            ProductWarehouseCost = self.env['product.location.cost']
            product = self.env['product.product'].browse(product_id)

            # Extract float value if cost is a dict
            cost_value = cost if isinstance(cost, (int, float)) else 0.0
            if product and warehouse_id:
                costing_method = product.cost_method
                if costing_method == 'fifo':
                    # For FIFO, always create a new record to maintain cost layers
                    ProductWarehouseCost.create({
                        'product_id': product_id,
                        'warehouse_id': warehouse_id,
                        'cost': cost,
                    })
                else:
                    existing = ProductWarehouseCost.search([
                        ('product_id', '=', product_id),
                        ('warehouse_id', '=', warehouse_id)
                    ], limit=1)
                
                    if existing:
                        existing.cost = cost_value
                    else:
                        ProductWarehouseCost.create({
                            'product_id': product_id,
                            'warehouse_id': warehouse_id,
                            'cost': cost_value,
                        })

        for move in self:
            if not move._is_in():
                continue
            if move.with_company(move.company_id).product_id.cost_method == 'standard':
                continue
            warehouse_dest_id = move.location_dest_id.warehouse_id.id
            product_tot_qty_available = move.product_id.with_context(warehouse_id = warehouse_dest_id).sudo().with_company(move.company_id).quantity_svl + tmpl_dict[move.product_id.id]
            rounding = move.product_id.uom_id.rounding

            valued_move_lines = move._get_in_move_lines()
            quantity_by_lot = defaultdict(float)
            if forced_qty:
                quantity_by_lot[forced_qty[0]] += forced_qty[1]
            else:
                for valued_move_line in valued_move_lines:
                    quantity_by_lot[valued_move_line.lot_id] += valued_move_line.product_uom_id._compute_quantity(valued_move_line.quantity, move.product_id.uom_id)

            qty = sum(quantity_by_lot.values())
            move_cost = move._get_price_unit()
            # self.result = move_cost
            warehouse_dest_cost = self.env['product.location.cost'].search([
                    ('product_id', '=', move.product_id.id),
                    ('warehouse_id', '=', warehouse_dest_id)
                ], order='id desc', limit=1)

            cost_dest_value = warehouse_dest_cost.cost if warehouse_dest_cost else 0.0
            if float_is_zero(product_tot_qty_available, precision_rounding=rounding) \
                    or float_is_zero(product_tot_qty_available + move.product_qty, precision_rounding=rounding) \
                    or float_is_zero(product_tot_qty_available + qty, precision_rounding=rounding):
                new_std_price = next(iter(move_cost.values()))
            else:
                # Get the standard price
                amount_unit = std_price_update.get((move.company_id.id, move.product_id.id, warehouse_dest_id)) or cost_dest_value
                new_std_price = ((amount_unit * product_tot_qty_available) + (next(iter(move_cost.values())) * qty)) / (product_tot_qty_available + qty)

            tmpl_dict[move.product_id.id] += qty
            # Write the standard price, as SUPERUSER_ID because a warehouse manager may not have the right to write on products
            move.product_id.with_company(move.company_id.id).with_context(disable_auto_svl=True).sudo().write({'standard_price': new_std_price})
            # FIFO Costing
            if move.with_company(move.company_id).product_id.cost_method == 'fifo':
                std_price_update[move.company_id.id, move.product_id.id, warehouse_dest_id] = move_cost
            else:
                # AVCO Costing
                std_price_update[move.company_id.id, move.product_id.id, warehouse_dest_id] = new_std_price
            
            # Update the standard price of the lot
            if not move.product_id.lot_valuated:
                continue
            for lot, qty in quantity_by_lot.items():
                qty_avail = lot.sudo().with_company(move.company_id).quantity_svl + lot_tmpl_dict[lot.id]
                if float_is_zero(qty_avail, precision_rounding=rounding) \
                        or float_is_zero(qty_avail + qty, precision_rounding=rounding):
                    new_std_price = move_cost[lot]
                else:
                    # Get the standard price
                    amount_unit = std_price_update_lot.get((move.company_id.id, lot.id)) or lot.with_company(move.company_id).standard_price
                    new_std_price = ((amount_unit * qty_avail) + (move_cost[lot] * qty)) / (qty_avail + qty)
                lot_tmpl_dict[lot.id] += qty
                lot.with_company(move.company_id.id).with_context(disable_auto_svl=True).sudo().standard_price = new_std_price
                std_price_update_lot[move.company_id.id, lot.id] = new_std_price
            
            
        # Update product.location.cost records
        for (company_id, product_id, warehouse_dest_id), cost in std_price_update.items():
            update_product_location_cost(product_id, warehouse_dest_id, cost)


    def _create_out_svl(self, forced_quantity=None):
        """Create a `stock.valuation.layer` from `self`.

        :param forced_quantity: under some circumstances, the quantity to value is different than
            the initial demand of the move (Default value = None). The lot to value is given in
            case of lot valuated product.
        :type forced_quantity: tuple(stock.lot, float)
        """
        svl_vals_list = self._get_out_svl_vals(forced_quantity)
        return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
    

    def _get_out_svl_vals(self, forced_quantity):
        svl_vals_list = []
        for move in self:
            move = move.with_company(move.company_id)
            warehouse_id = move.location_id.warehouse_id.id
            lines = move._get_out_move_lines()
            quantities = defaultdict(float)
            if forced_quantity:
                quantities[forced_quantity[0]] += forced_quantity[1]
            else:
                for line in lines:
                    quantities[line.lot_id] += line.product_uom_id._compute_quantity(
                        line.quantity, move.product_id.uom_id
                    )
            if float_is_zero(sum(quantities.values()), precision_rounding=move.product_id.uom_id.rounding):
                continue

            if move.product_id.lot_valuated:
                vals = []
                for lot_id, qty in quantities.items():
                    out_vals = move.product_id.with_context(warehouse_id = warehouse_id)._prepare_out_svl_vals(
                        qty,
                        move.company_id,
                        lot=lot_id
                    )
                    vals.append(out_vals)
            else:
                vals = [move.product_id.with_context(warehouse_id = warehouse_id)._prepare_out_svl_vals(sum(quantities.values()), move.company_id)]
            for val in vals:
                val.update(move._prepare_common_svl_vals())
                if forced_quantity:
                    val['description'] = _('Correction of %s (modification of past move)', move.picking_id.name or move.name)
                val['description'] += val.pop('rounding_adjustment', '')
            svl_vals_list += vals
        return svl_vals_list
        
    
    def _prepare_common_svl_vals(self):
            """When a `stock.valuation.layer` is created from a `stock.move`, we can prepare a dict of
            common vals.

            :returns: the common values when creating a `stock.valuation.layer` from a `stock.move`
            :rtype: dict
            """
            self.ensure_one()
            return {
                'stock_move_id': self.id,
                'warehouse_id': self.location_dest_id.warehouse_id.id if self._is_in() else self.location_id.warehouse_id.id,
                'company_id': self.company_id.id,
                'product_id': self.product_id.id,
                'description': self.reference and '%s - %s' % (self.reference, self.product_id.name) or self.product_id.name,
            }
    

    def _get_price_unit(self):
        """ Returns the unit price to value this stock move """
        self.ensure_one()
        price_unit = self.price_unit
        precision = self.env['decimal.precision'].precision_get('Product Price')
        # If the move is a return, use the original move's price unit.
        if self.origin_returned_move_id and self.origin_returned_move_id.sudo().stock_valuation_layer_ids:
            layers = self.origin_returned_move_id.sudo().stock_valuation_layer_ids
            
            # For EXI transfers, use direct unit cost
            if self.picking_type_id and self.picking_type_id.sequence_code == 'EXI':
                svl = layers[0]  # Get first layer
                return svl.unit_cost if not float_is_zero(svl.unit_cost, precision) else svl.value / svl.quantity
            
            if self.origin_returned_move_id._is_dropshipped() or self.origin_returned_move_id._is_dropshipped_returned():
                layers = layers.filtered(lambda l: float_compare(l.value, 0, precision_rounding=l.product_id.uom_id.rounding) <= 0)
            layers |= layers.stock_valuation_layer_ids
            if self.product_id.lot_valuated:
                layers_by_lot = layers.grouped('lot_id')
                prices = defaultdict(lambda: 0)
                for lot, stock_layers in layers_by_lot.items():
                    qty = sum(stock_layers.mapped("quantity"))
                    val = sum(stock_layers.mapped("value"))
                    prices[lot] = val / qty if not float_is_zero(qty, precision_rounding=self.product_id.uom_id.rounding) else 0
            else:
                quantity = sum(layers.mapped("quantity"))
                prices = {self.env['stock.lot']: sum(layers.mapped("value")) / quantity if not float_is_zero(quantity, precision_rounding=layers.uom_id.rounding) else 0}
            return prices
        
        
        if not float_is_zero(price_unit, precision) or self._should_force_price_unit():
            if self.product_id.lot_valuated:
                return dict.fromkeys(self.lot_ids, price_unit)
            else:
                return {self.env['stock.lot']: price_unit}
        else:
            if self.product_id.lot_valuated:
                return {lot: lot.standard_price or self.product_id.standard_price for lot in self.lot_ids}
            else:
                warehouse_id = (self.location_dest_id.warehouse_id.id if self._is_in()
                            else self.location_id.warehouse_id.id)
                warehouse_cost = self.env['product.location.cost'].search([
                    ('product_id', '=', self.product_id.id),
                    ('warehouse_id', '=', warehouse_id)
                ], order='id desc', limit=1) if warehouse_id else False
                cost = warehouse_cost.cost if warehouse_cost else 0.0
                return {self.env['stock.lot']: cost}
    
    