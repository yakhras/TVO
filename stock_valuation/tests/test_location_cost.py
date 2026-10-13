# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import StockValuationCommon


@tagged('post_install', '-at_install')
class TestLocationCost(StockValuationCommon):

    def test_cost_change_writes_history(self):
        cost = self.env['product.location.cost'].create({
            'product_id': self.product.id,
            'warehouse_id': self.wh1.id,
            'cost': 10.0,
        })
        self.assertFalse(cost.history_ids)

        cost.cost = 12.5
        self.assertEqual(len(cost.history_ids), 1)
        hist = cost.history_ids
        self.assertEqual(hist.old_cost, 10.0)
        self.assertEqual(hist.new_cost, 12.5)
        self.assertAlmostEqual(hist.cost_difference, 2.5)
        self.assertAlmostEqual(hist.cost_change_percent, 25.0)
        self.assertEqual(hist.changed_by, self.env.user)
        self.assertEqual(hist.warehouse_id, self.wh1)
        self.assertEqual(hist.product_id, self.product)

    def test_same_cost_writes_no_history(self):
        cost = self.env['product.location.cost'].create({
            'product_id': self.product.id,
            'warehouse_id': self.wh1.id,
            'cost': 10.0,
        })
        cost.cost = 10.0
        self.assertFalse(cost.history_ids)

    def test_percent_from_zero_cost(self):
        cost = self.env['product.location.cost'].create({
            'product_id': self.product.id,
            'warehouse_id': self.wh1.id,
            'cost': 0.0,
        })
        cost.cost = 5.0
        self.assertEqual(cost.history_ids.cost_change_percent, 0.0)
        self.assertEqual(cost.history_ids.cost_difference, 5.0)

    def test_stock_user_has_access(self):
        user = self.env['res.users'].create({
            'name': 'SV Stock User',
            'login': 'sv_stock_user',
            'groups_id': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        cost = self.env['product.location.cost'].with_user(user).create({
            'product_id': self.product.id,
            'warehouse_id': self.wh1.id,
            'cost': 1.0,
        })
        cost.cost = 2.0
        self.assertEqual(len(cost.sudo().history_ids), 1)
