# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StockValuationCommon


@tagged('post_install', '-at_install')
class TestRevaluation(StockValuationCommon):

    def _wizard(self, wh, added_value):
        return self.env['stock.valuation.layer.revaluation'].with_context(
            default_product_id=self.product.id,
            default_company_id=self.company.id,
        ).create({
            'warehouse_id': wh.id,
            'added_value': added_value,
            'reason': 'SV test',
        })

    def test_wizard_shows_warehouse_stock(self):
        self._receive(self.wh1, 10, 10.0)
        self._receive(self.wh2, 4, 25.0)
        wiz = self._wizard(self.wh2, 1.0)
        self.assertEqual(wiz.current_quantity_svl, 4)
        self.assertAlmostEqual(wiz.current_value_svl, 100.0)

    def test_revaluation_updates_warehouse_cost(self):
        self._receive(self.wh1, 10, 10.0)
        self._receive(self.wh2, 10, 10.0)

        self._wizard(self.wh1, 100.0).action_validate_revaluation()

        self.assertAlmostEqual(self._costs(self.wh1).cost, 20.0)
        self.assertAlmostEqual(self._costs(self.wh2).cost, 10.0)
        self.assertEqual(self._wh_svl(self.wh1), (10, 200.0))
        self.assertEqual(self._wh_svl(self.wh2), (10, 100.0))
        reval = self.env['stock.valuation.layer'].search([
            ('product_id', '=', self.product.id),
            ('quantity', '=', 0),
        ])
        self.assertEqual(reval.warehouse_id, self.wh1)
        self.assertAlmostEqual(reval.value, 100.0)

    def test_zero_value_is_refused(self):
        self._receive(self.wh1, 10, 10.0)
        with self.assertRaises(UserError):
            self._wizard(self.wh1, 0.0).action_validate_revaluation()
