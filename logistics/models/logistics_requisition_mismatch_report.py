from odoo import fields, models
from odoo.tools.sql import SQL


class LogisticsRequisitionMismatchReport(models.Model):
    _name = 'logistics.requisition.mismatch.report'
    _description = 'Purchase Agreement vs Container Quantity Mismatch'
    _auto = False
    _order = 'requisition_id, product_id'

    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement', readonly=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit', readonly=True)
    ordered_qty = fields.Float(string='Agreed Quantity', readonly=True)
    shipped_qty = fields.Float(string='Container Quantity', readonly=True)
    variance_qty = fields.Float(string='Variance', readonly=True)
    mismatch_type = fields.Selection(
        [
            ('increase', 'Over Allocated'),
            ('decrease', 'Under Allocated'),
            ('match', 'Matched'),
        ],
        string='Mismatch', readonly=True,
    )
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    @property
    def _table_query(self):
        return SQL("%s %s %s", self._select(), self._from(), self._where())

    def _select(self):
        return SQL("""
            SELECT
                ROW_NUMBER() OVER (ORDER BY prl.requisition_id, prl.product_id) AS id,
                prl.requisition_id AS requisition_id,
                pr.vendor_id AS vendor_id,
                prl.product_id AS product_id,
                prl.product_uom_id AS product_uom_id,
                prl.product_qty AS ordered_qty,
                COALESCE(cl.shipped_qty, 0.0) AS shipped_qty,
                COALESCE(cl.shipped_qty, 0.0) - prl.product_qty AS variance_qty,
                CASE
                    WHEN COALESCE(cl.shipped_qty, 0.0) > prl.product_qty THEN 'increase'
                    WHEN COALESCE(cl.shipped_qty, 0.0) < prl.product_qty THEN 'decrease'
                    ELSE 'match'
                END AS mismatch_type,
                prl.company_id AS company_id
        """)

    def _from(self):
        return SQL("""
            FROM purchase_requisition_line prl
            JOIN purchase_requisition pr ON pr.id = prl.requisition_id
            LEFT JOIN (
                SELECT requisition_id, product_id, SUM(product_qty) AS shipped_qty
                FROM logistics_container_line
                WHERE requisition_id IS NOT NULL AND product_id IS NOT NULL
                GROUP BY requisition_id, product_id
            ) cl ON cl.requisition_id = prl.requisition_id AND cl.product_id = prl.product_id
        """)

    def _where(self):
        return SQL("""
            WHERE prl.product_id IS NOT NULL
        """)

    def action_open_requisition(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.requisition',
            'res_id': self.requisition_id.id,
            'views': [(False, 'form')],
            'target': 'current',
        }
