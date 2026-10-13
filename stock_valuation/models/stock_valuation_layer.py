# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, tools
from odoo.tools import float_compare, float_is_zero


class StockValuationLayer(models.Model):

    _inherit = 'stock.valuation.layer'

    warehouse_id = fields.Many2one(
        'stock.warehouse', 
        string='Warehouse', 
        readonly=False, 
        index=True,
        store=True,)

    unit_cost = fields.Float(readonly=False)
    value = fields.Monetary(readonly=False)
    description = fields.Char(readonly=False)
    