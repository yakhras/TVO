# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase


class StockValuationCommon(TransactionCase):
    """Two fresh warehouses and an AVCO product, so the tests never touch
    existing stock or costs in the database they run on."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.wh1 = cls.env['stock.warehouse'].create({'name': 'SV Test WH1', 'code': 'SVW1'})
        cls.wh2 = cls.env['stock.warehouse'].create({'name': 'SV Test WH2', 'code': 'SVW2'})
        cls.supplier_loc = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_loc = cls.env.ref('stock.stock_location_customers')
        cls.categ_avco = cls.env['product.category'].create({
            'name': 'SV Test AVCO',
            'property_cost_method': 'average',
            'property_valuation': 'manual_periodic',
        })
        cls.categ_fifo = cls.env['product.category'].create({
            'name': 'SV Test FIFO',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'SV Test Product',
            'is_storable': True,
            'categ_id': cls.categ_avco.id,
        })

    # -- helpers -----------------------------------------------------------

    def _move(self, product, src, dest, qty, price=0.0, picking_type=None):
        move = self.env['stock.move'].create({
            'name': 'SV test move',
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': qty,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'price_unit': price,
            'picking_type_id': picking_type.id if picking_type else False,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def _receive(self, wh, qty, price, product=None):
        return self._move(product or self.product, self.supplier_loc, wh.lot_stock_id,
                          qty, price, wh.in_type_id)

    def _deliver(self, wh, qty, product=None):
        return self._move(product or self.product, wh.lot_stock_id, self.customer_loc,
                          qty, picking_type=wh.out_type_id)

    def _validate_picking(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()

    def _receipt_picking(self, wh, qty, price, product=None):
        product = product or self.product
        picking = self.env['stock.picking'].create({
            'picking_type_id': wh.in_type_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': wh.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'name': product.name,
                'product_id': product.id,
                'product_uom': product.uom_id.id,
                'product_uom_qty': qty,
                'price_unit': price,
                'location_id': self.supplier_loc.id,
                'location_dest_id': wh.lot_stock_id.id,
            })],
        })
        self._validate_picking(picking)
        return picking

    def _costs(self, wh, product=None):
        return self.env['product.location.cost'].search([
            ('product_id', '=', (product or self.product).id),
            ('warehouse_id', '=', wh.id),
        ], order='id')

    def _wh_svl(self, wh, product=None):
        product = (product or self.product).with_context(warehouse_id=wh.id)
        return product.quantity_svl, product.value_svl
