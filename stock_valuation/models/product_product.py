# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, fields, api
from odoo.tools import float_is_zero, float_repr, float_compare


class ProductProduct(models.Model):
    _inherit = 'product.product'


    result = fields.Text('Result')
    location_cost_ids = fields.One2many('product.location.cost', 'product_id', string='Location Costs')


    @api.depends('stock_valuation_layer_ids')
    @api.depends_context('to_date', 'company', 'warehouse_id')
    def _compute_value_svl(self):
        """Compute `value_svl` and `quantity_svl`."""
        company_id = self.env.company
        self.company_currency_id = company_id.currency_id
        domain = [
            *self.env['stock.valuation.layer']._check_company_domain(company_id),
            ('product_id', 'in', self.ids),
        ]
        if self.env.context.get('to_date'):
            to_date = fields.Datetime.to_datetime(self.env.context['to_date'])
            domain.append(('create_date', '<=', to_date))
        warehouse_id = self.env.context.get('warehouse_id')
        # self.result  = warehouse_id
        if warehouse_id:
            domain.extend([('warehouse_id.id', '=', warehouse_id)])

        groups = self.env['stock.valuation.layer']._read_group(
            domain,
            groupby=['product_id'],
            aggregates=['value:sum', 'quantity:sum'],
        )
        
        # Browse all products and compute products' quantities_dict in batch.
        group_mapping = {product: aggregates for product, *aggregates in groups}
        for product in self:
            value_sum, quantity_sum = group_mapping.get(product._origin, (0, 0))
            value_svl = company_id.currency_id.round(value_sum)
            avg_cost = value_svl / quantity_sum if quantity_sum else 0
            product.value_svl = value_svl
            product.quantity_svl = quantity_sum
            product.avg_cost = avg_cost
            product.total_value = avg_cost * product.sudo(False).qty_available
        

    def _prepare_out_svl_vals(self, quantity, company, lot=False):
        """Prepare the values for a stock valuation layer created by a delivery.

        :param quantity: the quantity to value, expressed in `self.uom_id`
        :return: values to use in a call to create
        :rtype: dict
        """
        self.ensure_one()
        company_id = self.env.context.get('force_company', self.env.company.id)
        company = self.env['res.company'].browse(company_id)
        currency = company.currency_id
        product_id = self.id  # Assuming this method runs in the product.product model
        warehouse_id = self.env.context.get('warehouse_id')
        # self.result = warehouse_id

        # Quantity is negative for out valuation layers.
        quantity = -1 * quantity
        warehouse_cost = self.env['product.location.cost'].search([
            ('product_id', '=', product_id),
            ('warehouse_id', '=', warehouse_id)
        ], order='id desc', limit=1) if (warehouse_id and product_id) else False

        cost_value = warehouse_cost.cost if warehouse_cost else 0.0
        vals = {
            'product_id': product_id,
            'value': currency.round(quantity * cost_value),
            'unit_cost': cost_value,
            'quantity': quantity,
            'lot_id': lot.id if lot else False,
        }
        fifo_vals = self._run_fifo(abs(quantity), company, lot=lot)
        vals['remaining_qty'] = fifo_vals.get('remaining_qty')
        # In case of AVCO, fix rounding issue of standard price when needed.
        if self.product_tmpl_id.cost_method == 'average' and not float_is_zero(self.quantity_svl, precision_rounding=self.uom_id.rounding):
            rounding_error = currency.round(
                (cost_value * self.quantity_svl - self.value_svl) * abs(quantity / self.quantity_svl)
            )
            # If it is bigger than the (smallest number of the currency * quantity) / 2,
            # then it isn't a rounding error but a stock valuation error, we shouldn't fix it under the hood ...
            threshold = currency.round(max((abs(quantity) * currency.rounding) / 2, currency.rounding))
            if rounding_error and abs(rounding_error) <= threshold:
                vals['value'] += rounding_error
                vals['rounding_adjustment'] = '\nRounding Adjustment: %s%s %s' % (
                    '+' if rounding_error > 0 else '',
                    float_repr(rounding_error, precision_digits=currency.decimal_places),
                    currency.symbol
                )
        if self.product_tmpl_id.cost_method == 'fifo':
            vals.update(fifo_vals)
        return vals
    

    def _get_fifo_candidates_domain(self, company, lot=False):
        domain = [
            ("product_id", "=", self.id),
            ("remaining_qty", ">", 0),
            ("company_id", "=", company.id),
            ("lot_id", "=", lot.id if lot else False),
        ]
        
        warehouse_id = self.env.context.get('warehouse_id')
        if warehouse_id:
            domain.append(("warehouse_id", "=", warehouse_id))
        
        return domain
        

    def _run_fifo(self, quantity, company, lot=False):
        self.ensure_one()

        # Find back incoming stock valuation layers (called candidates here) to value `quantity`.
        qty_to_take_on_candidates = quantity
        candidates = self._get_fifo_candidates(company, lot=lot)
        new_standard_price = 0
        tmp_value = 0  # to accumulate the value taken on the candidates
        for candidate in candidates:
            qty_taken_on_candidate = self._get_qty_taken_on_candidate(qty_to_take_on_candidates, candidate)

            candidate_unit_cost = candidate.remaining_value / candidate.remaining_qty
            new_standard_price = candidate_unit_cost
            value_taken_on_candidate = qty_taken_on_candidate * candidate_unit_cost
            value_taken_on_candidate = candidate.currency_id.round(value_taken_on_candidate)
            new_remaining_value = candidate.remaining_value - value_taken_on_candidate

            candidate_vals = {
                'remaining_qty': candidate.remaining_qty - qty_taken_on_candidate,
                'remaining_value': new_remaining_value,
            }

            candidate.write(candidate_vals)

            qty_to_take_on_candidates -= qty_taken_on_candidate
            tmp_value += value_taken_on_candidate

            
            if float_is_zero(candidate.remaining_qty, precision_rounding=self.uom_id.rounding):
                if self.cost_method == 'fifo':
                    ProductWarehouseCost = self.env['product.location.cost']
                    oldest_cost = ProductWarehouseCost.sudo().search([
                        ('product_id', '=', self.id),
                        ('warehouse_id', '=', candidate.warehouse_id.id)
                    ], order='create_date asc', limit=1)
                    
                    if oldest_cost:
                        oldest_cost.sudo().unlink()
                if float_is_zero(qty_to_take_on_candidates, precision_rounding=self.uom_id.rounding):
                    next_candidates = candidates.filtered(lambda svl: svl.remaining_qty > 0)
                    new_standard_price = next_candidates and next_candidates[0].unit_cost or new_standard_price
                    break

        # Fifo out will change the AVCO value of the product. So in case of out,
        # we recompute it base on the remaining value and quantities.
        if self.cost_method == 'fifo':
            quantity_svl = sum(candidates.mapped('remaining_qty'))
            value_svl = sum(candidates.mapped('remaining_value'))
            product = self.sudo().with_company(company.id).with_context(disable_auto_svl=True)
            if float_compare(quantity_svl, 0.0, precision_rounding=self.uom_id.rounding) > 0:
                product.standard_price = value_svl / quantity_svl
            elif candidates and not float_is_zero(qty_to_take_on_candidates, precision_rounding=self.uom_id.rounding):
                product.standard_price = new_standard_price

        # If there's still quantity to value but we're out of candidates, we fall in the
        # negative stock use case. We chose to value the out move at the price of the
        # last out and a correction entry will be made once `_fifo_vacuum` is called.
        vals = {}
        if float_is_zero(qty_to_take_on_candidates, precision_rounding=self.uom_id.rounding):
            vals = {
                'value': -tmp_value,
                'unit_cost': tmp_value / quantity,
            }
        else:
            assert qty_to_take_on_candidates > 0
            last_fifo_price = new_standard_price or self.standard_price
            negative_stock_value = last_fifo_price * -qty_to_take_on_candidates
            tmp_value += abs(negative_stock_value)
            vals = {
                'remaining_qty': -qty_to_take_on_candidates,
                'value': -tmp_value,
                'unit_cost': last_fifo_price,
            }
        return vals
             
