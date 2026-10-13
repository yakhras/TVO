# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import StockValuationCommon


@tagged('post_install', '-at_install')
class TestValuationFlow(StockValuationCommon):

    def test_receipt_sets_warehouse_cost(self):
        move = self._receive(self.wh1, 10, 5.0)

        costs = self._costs(self.wh1)
        self.assertEqual(len(costs), 1)
        self.assertEqual(costs.cost, 5.0)
        self.assertFalse(self._costs(self.wh2))
        self.assertEqual(move.stock_valuation_layer_ids.warehouse_id, self.wh1)
        self.assertEqual(self._wh_svl(self.wh1), (10, 50.0))

    def test_avco_is_kept_per_warehouse(self):
        self._receive(self.wh1, 10, 5.0)
        self._receive(self.wh1, 10, 15.0)
        self._receive(self.wh2, 10, 100.0)

        wh1_cost = self._costs(self.wh1)
        self.assertEqual(len(wh1_cost), 1, "AVCO keeps one cost record per warehouse")
        self.assertAlmostEqual(wh1_cost.cost, 10.0)
        self.assertAlmostEqual(self._costs(self.wh2).cost, 100.0)
        self.assertEqual(self._wh_svl(self.wh1), (20, 200.0))
        self.assertEqual(self._wh_svl(self.wh2), (10, 1000.0))
        # the second WH1 receipt is logged as a cost change 5 -> 10
        self.assertEqual(wh1_cost.history_ids.mapped('old_cost'), [5.0])
        self.assertEqual(wh1_cost.history_ids.mapped('new_cost'), [10.0])

    def test_delivery_valued_at_warehouse_cost(self):
        self._receive(self.wh1, 10, 10.0)
        self._receive(self.wh2, 10, 30.0)

        out1 = self._deliver(self.wh1, 4)
        out2 = self._deliver(self.wh2, 2)

        svl1 = out1.stock_valuation_layer_ids
        self.assertEqual(svl1.warehouse_id, self.wh1)
        self.assertEqual(svl1.quantity, -4)
        self.assertAlmostEqual(svl1.value, -40.0)
        self.assertAlmostEqual(svl1.unit_cost, 10.0)
        svl2 = out2.stock_valuation_layer_ids
        self.assertEqual(svl2.warehouse_id, self.wh2)
        self.assertAlmostEqual(svl2.value, -60.0)
        self.assertEqual(self._wh_svl(self.wh1), (6, 60.0))
        self.assertEqual(self._wh_svl(self.wh2), (8, 240.0))
        # a delivery does not change the AVCO cost
        self.assertAlmostEqual(self._costs(self.wh1).cost, 10.0)

    def test_receipt_after_stock_emptied_restarts_cost(self):
        self._receive(self.wh1, 5, 10.0)
        self._deliver(self.wh1, 5)
        self._receive(self.wh1, 5, 20.0)
        self.assertAlmostEqual(self._costs(self.wh1).cost, 20.0)

    def test_quant_value_uses_warehouse_cost(self):
        self._receive(self.wh1, 10, 7.0)
        self._receive(self.wh2, 3, 50.0)
        quant1 = self.env['stock.quant'].search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', self.wh1.lot_stock_id.id),
        ])
        quant2 = self.env['stock.quant'].search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', self.wh2.lot_stock_id.id),
        ])
        self.assertAlmostEqual(quant1.value, 70.0)
        self.assertAlmostEqual(quant1.unit_value, 7.0)
        self.assertAlmostEqual(quant2.value, 150.0)
        self.assertAlmostEqual(quant2.unit_value, 50.0)

    def test_fifo_receipt_known_bug(self):
        """Pins a known bug, so a fix shows up as a failing test to update.

        For FIFO, product_price_update_before_done stores the whole
        {lot: price} dict from _get_price_unit() (stock_move.py:97) and then
        writes it into the Float `cost` field, so any FIFO receipt raises.
        All products in use are AVCO. Once fixed, replace the assertRaises
        with: two receipts 5.0 / 7.0 -> costs [5.0, 7.0] (one record each).
        """
        fifo = self.env['product.product'].create({
            'name': 'SV Test FIFO Product',
            'is_storable': True,
            'categ_id': self.categ_fifo.id,
        })
        with self.assertRaises(TypeError):
            self._receive(self.wh1, 10, 5.0, product=fifo)
