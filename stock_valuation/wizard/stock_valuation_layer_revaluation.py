# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, format_list


class StockValuationLayerRevaluation(models.TransientModel):
    _inherit = 'stock.valuation.layer.revaluation'


    warehouse_id = fields.Many2one('stock.warehouse', required=True)


    @api.depends('product_id', 'warehouse_id', 'adjusted_layer_ids', 'lot_id')
    def _compute_current_value_svl(self):
        for reval in self:
            if reval.adjusted_layer_ids:
                reval.current_quantity_svl = sum(reval.adjusted_layer_ids.filtered([('warehouse_id', '=', reval.warehouse_id)]).mapped('remaining_qty'))
                reval.current_value_svl = sum(reval.adjusted_layer_ids.filtered([('warehouse_id', '=', reval.warehouse_id)]).mapped('remaining_value'))
            if reval.lot_id:
                reval.current_quantity_svl = reval.lot_id.quantity_svl
                reval.current_value_svl = reval.lot_id.value_svl
            else:
                reval.current_quantity_svl = reval.product_id.with_context(warehouse_id=reval.warehouse_id.id).quantity_svl
                reval.current_value_svl = reval.product_id.with_context(warehouse_id=reval.warehouse_id.id).value_svl



    def action_validate_revaluation(self):
        """ Adjust the valuation of layers `self.adjusted_layer_ids` for
        `self.product_id` in `self.company_id`, or the entire stock for that
        product if no layers are specified (all layers with positive remaining
        quantity).

        - Change the standard price with the new valuation by product unit.
        - Create a manual stock valuation layer with the `added_value` of `self`.
        - Distribute the `added_value` on the remaining_value of the layers
        - If the Inventory Valuation of the product category is automated, create
        related account move.
        """
        self.ensure_one()
        if self.currency_id.is_zero(self.added_value):
            raise UserError(_("The added value doesn't have any impact on the stock valuation"))

        product_id = self.product_id.with_company(self.company_id)
        lot_id = self.lot_id.with_company(self.company_id)

        remaining_domain = [
            ('product_id', '=', product_id.id),
            ('warehouse_id', '=', self.warehouse_id.id),
            ('remaining_qty', '>', 0),
            ('company_id', '=', self.company_id.id),
        ]
        if lot_id:
            remaining_domain.append(('lot_id', '=', lot_id.id))
        layers_with_qty = self.env['stock.valuation.layer'].search(remaining_domain)
        adjusted_layers = self.adjusted_layer_ids or layers_with_qty
        
        

        if product_id and self.warehouse_id:
            # Check if a record already exists
            warehouse_cost = self.env['product.location.cost'].search([
                ('product_id', '=', product_id.id),
                ('warehouse_id', '=', self.warehouse_id.id)
            ], limit=1)

        cost_value = warehouse_cost.cost if warehouse_cost else 0.0
        description = _("Manual Stock Valuation: %s.", self.reason or _("No Reason Given"))
        cost_method = product_id.categ_id.property_cost_method
        if cost_method in ['average', 'fifo']:
            previous_cost = lot_id.standard_price if lot_id else cost_value
            total_product_qty = sum(layers_with_qty.mapped('remaining_qty'))
            if lot_id:
                lot_id.with_context(disable_auto_svl=True).standard_price += self.added_value / total_product_qty
            warehouse_cost.cost += self.added_value / product_id.with_context(warehouse_id=self.warehouse_id.id).quantity_svl
            product_id.with_company(self.company_id).with_context(disable_auto_svl=True).sudo().write({'standard_price': warehouse_cost.cost})
            if self.lot_id:
                description += _(
                    " lot/serial number cost updated from %(previous)s to %(new_cost)s.",
                    previous=previous_cost,
                    new_cost=lot_id.standard_price
                )
            else:
                description += _(
                    " Product cost updated from %(previous)s to %(new_cost)s.",
                    previous=previous_cost,
                    new_cost=warehouse_cost.cost
                )
        
        
        revaluation_svl_vals = {
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id,
            'product_id': product_id.id,
            'description': description,
            'value': self.added_value,
            'lot_id': self.lot_id.id,
            'quantity': 0,
        }

        qty_by_lots = defaultdict(float)

        remaining_qty = sum(adjusted_layers.mapped('remaining_qty'))
        remaining_value = self.added_value
        remaining_value_unit_cost = self.currency_id.round(remaining_value / remaining_qty)
        
        # adjust all layers by the unit value change per unit, except the last layer which gets
        # whatever is left. This avoids rounding issues e.g. $10 on 3 products => 3.33, 3.33, 3.34
        for svl in adjusted_layers:
            if product_id.lot_valuated and not lot_id:
                qty_by_lots[svl.lot_id.id] += svl.remaining_qty
            if float_is_zero(svl.remaining_qty - remaining_qty, precision_rounding=self.product_id.uom_id.rounding):
                taken_remaining_value = remaining_value
            else:
                taken_remaining_value = remaining_value_unit_cost * svl.remaining_qty
            if float_compare(svl.remaining_value + taken_remaining_value, 0, precision_rounding=self.product_id.uom_id.rounding) < 0:
                raise UserError(_('The value of a stock valuation layer cannot be negative. Landed cost could be use to correct a specific transfer.'))
            
            svl.remaining_value += taken_remaining_value
            remaining_value -= taken_remaining_value
            remaining_qty -= svl.remaining_qty

        previous_value_svl = self.current_value_svl

        if qty_by_lots:
            vals = revaluation_svl_vals.copy()
            total_qty = sum(adjusted_layers.mapped('remaining_qty'))
            revaluation_svl_vals = []
            for lot, qty in qty_by_lots.items():
                value = self.added_value * qty / total_qty
                revaluation_svl_vals.append(
                    dict(vals, value=value, lot_id=lot)
                )

        revaluation_svl = self.env['stock.valuation.layer'].create(revaluation_svl_vals)

        # If the Inventory Valuation of the product category is automated, create related account move.
        if self.property_valuation != 'real_time':
            return True
        
        

        accounts = product_id.product_tmpl_id.get_product_accounts()

        if self.added_value < 0:
            debit_account_id = self.account_id.id
            credit_account_id = accounts.get('stock_valuation') and accounts['stock_valuation'].id
        else:
            debit_account_id = accounts.get('stock_valuation') and accounts['stock_valuation'].id
            credit_account_id = self.account_id.id

        move_description = _('%(user)s changed stock valuation from  %(previous)s to %(new_value)s - %(product)s\n%(reason)s',
            user=self.env.user.name,
            previous=previous_value_svl,
            new_value=previous_value_svl + self.added_value,
            product=product_id.display_name,
            reason=description,
        )

        if self.adjusted_layer_ids:
            adjusted_layer_descriptions = [f"{layer.reference} (id: {layer.id})" for layer in self.adjusted_layer_ids]
            move_description += _("\nAffected valuation layers: %s", format_list(self.env, adjusted_layer_descriptions))


        move_vals = [{
            'journal_id': self.account_journal_id.id or accounts['stock_journal'].id,
            'company_id': self.company_id.id,
            'ref': _("Revaluation of %s", product_id.display_name),
            'stock_valuation_layer_ids': [(6, None, [svl.id])],
            'date': self.date or fields.Date.today(),
            'move_type': 'entry',
            'line_ids': [(0, 0, {
                'name': move_description,
                'account_id': debit_account_id,
                'debit': abs(svl.value),
                'credit': 0,
                'product_id': svl.product_id.id,
            }), (0, 0, {
                'name': move_description,
                'account_id': credit_account_id,
                'debit': 0,
                'credit': abs(svl.value),
                'product_id': svl.product_id.id,
            })],
        } for svl in revaluation_svl]
        account_move = self.env['account.move'].create(move_vals)
        account_move._post()

        return True
        
    
