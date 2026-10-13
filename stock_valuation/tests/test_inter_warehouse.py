# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import StockValuationCommon


@tagged('post_install', '-at_install')
class TestInterWarehouse(StockValuationCommon):
    """EXO (WH1 stock -> transit) creates an EXI (transit -> WH2 stock) that
    carries the WH1 cost into WH2."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.transit = cls.env['stock.location'].create({
            'name': 'SV Test Transit',
            'usage': 'transit',
            'company_id': cls.company.id,
        })
        cls.exo_type = cls._picking_type('EXO', cls.wh1, cls.wh1.lot_stock_id, cls.transit)
        cls.exi_type = cls.env['stock.picking.type'].search([('sequence_code', '=', 'EXI')], limit=1) \
            or cls._picking_type('EXI', cls.wh2, cls.transit, cls.wh2.lot_stock_id)

    @classmethod
    def _picking_type(cls, code, wh, src, dest):
        return cls.env['stock.picking.type'].create({
            'name': 'SV Test %s' % code,
            'sequence_code': code,
            'code': 'internal',
            'warehouse_id': wh.id,
            'default_location_src_id': src.id,
            'default_location_dest_id': dest.id,
        })

    def test_exo_creates_exi_and_moves_value(self):
        self._receive(self.wh1, 10, 10.0)
        self._receive(self.wh2, 10, 40.0)

        exo = self.env['stock.picking'].create({
            'picking_type_id': self.exo_type.id,
            'location_id': self.wh1.lot_stock_id.id,
            'location_dest_id': self.transit.id,
            'destination': self.wh2.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'name': self.product.name,
                'product_id': self.product.id,
                'product_uom': self.product.uom_id.id,
                'product_uom_qty': 4,
                'location_id': self.wh1.lot_stock_id.id,
                'location_dest_id': self.transit.id,
            })],
        })
        self._validate_picking(exo)

        self.assertEqual(self._wh_svl(self.wh1), (6, 60.0))
        exi = self.env['stock.picking'].search([('origin', '=', exo.name)])
        self.assertEqual(len(exi), 1)
        self.assertEqual(exi.picking_type_id.sequence_code, 'EXI')
        self.assertEqual(exi.location_dest_id, self.wh2.lot_stock_id)
        self.assertEqual(exi.move_ids.origin_returned_move_id, exo.move_ids)

        self._validate_picking(exi)

        # WH2: 10 @ 40 + 4 @ 10 = 440 / 14
        self.assertEqual(self._wh_svl(self.wh2), (14, 440.0))
        self.assertAlmostEqual(self._costs(self.wh2).cost, 440.0 / 14, places=2)
        self.assertAlmostEqual(self._costs(self.wh1).cost, 10.0)
