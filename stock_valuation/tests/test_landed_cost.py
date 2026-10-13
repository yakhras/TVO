# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import StockValuationCommon


@tagged('post_install', '-at_install')
class TestLandedCost(StockValuationCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.freight = cls.env['product.product'].create({
            'name': 'SV Test Freight',
            'type': 'service',
            'landed_cost_ok': True,
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'SV Test Landed Costs',
            'code': 'SVLC',
            'type': 'general',
        })

    def _landed_cost(self, picking, amount):
        lc = self.env['stock.landed.cost'].create({
            'picking_ids': [(6, 0, picking.ids)],
            'account_journal_id': self.journal.id,
            'cost_lines': [(0, 0, {
                'name': 'Freight',
                'product_id': self.freight.id,
                'price_unit': amount,
                'split_method': 'equal',
            })],
        })
        lc.compute_landed_cost()
        lc.button_validate()
        return lc

    def test_landed_cost_raises_warehouse_cost(self):
        picking = self._receipt_picking(self.wh1, 10, 10.0)
        self._receive(self.wh2, 10, 10.0)

        lc = self._landed_cost(picking, 50.0)

        self.assertEqual(lc.state, 'done')
        self.assertEqual(lc.warehouse_id, self.wh1)
        self.assertAlmostEqual(self._costs(self.wh1).cost, 15.0)
        self.assertAlmostEqual(self._costs(self.wh2).cost, 10.0, msg="other warehouse untouched")
        self.assertEqual(self._wh_svl(self.wh1), (10, 150.0))
        lc_layer = lc.stock_valuation_layer_ids
        self.assertEqual(lc_layer.warehouse_id, self.wh1)
        self.assertAlmostEqual(lc_layer.value, 50.0)

    def test_landed_cost_prorated_to_remaining_stock(self):
        picking = self._receipt_picking(self.wh1, 10, 10.0)
        self._deliver(self.wh1, 5)

        lc = self._landed_cost(picking, 50.0)

        # only the 5 units still in stock carry the landed cost: 50 * 5/10
        self.assertAlmostEqual(lc.stock_valuation_layer_ids.value, 25.0)
        self.assertAlmostEqual(self._costs(self.wh1).cost, 15.0)
