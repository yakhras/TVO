from odoo import fields, models
from odoo.tools.sql import SQL

from .logistics_container import CONTAINER_STATE_SELECTION


class LogisticsBillLadingReport(models.Model):
    """One row per B/L + product (+ vendor, company), aggregated from container lines,
    like the arrival reports. Clicking a row opens the container lines behind it.

    Purchase Agreement, Container Type and Invoice No can differ between the
    lines of one B/L + product, so they are shown as comma-joined text."""
    _name = 'logistics.bill.lading.report'
    _description = 'Bill of Lading Analysis'
    _auto = False
    _order = 'arrival_date desc, bill_lading_id, product_id'

    # === MEASURES ===
    product_qty = fields.Float(
        string='Quantity', digits='Product Unit of Measure', readonly=True,
    )
    container_count = fields.Integer(string='Count (Container)', readonly=True)
    # Comma-joined container ids, only used to count distinct containers
    # across rows when grouping (see _read_group_select).
    container_ids_text = fields.Char(readonly=True)

    # === DIMENSIONS ===
    bill_lading_id = fields.Many2one('logistics.bill.lading', string='BL', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_description = fields.Text(
        related='product_id.description_picking', string='Product Description',
    )
    requisition_names = fields.Char(string='Purchase Agreement', readonly=True)
    container_types = fields.Char(string='Container Type', readonly=True)
    invoice_nos = fields.Char(string='Invoice No', readonly=True)
    docs_draft = fields.Boolean(string='Docs Draft', readonly=True)
    docs_original = fields.Boolean(string='Docs Org', readonly=True)
    bl_original_release = fields.Boolean(string='BL Org./Release', readonly=True)
    coo = fields.Boolean(string='COO', readonly=True)
    coa = fields.Boolean(string='COA', readonly=True)
    hc = fields.Boolean(string='HC', readonly=True)
    mtfta = fields.Boolean(string='MTFTA', readonly=True)
    shipping_line_id = fields.Many2one(
        'logistics.shipping.line', string='Shipping Line', readonly=True,
    )
    arrival_date = fields.Date(string='Arriving Date', readonly=True)
    port_of_discharge_id = fields.Many2one('logistics.port', string='Port To', readonly=True)
    state = fields.Selection(CONTAINER_STATE_SELECTION, string='Status', readonly=True)
    child_state_id = fields.Many2one(
        'logistics.container.child.state', string='Child State', readonly=True,
    )
    # Filter / group-by only (not a list column).
    vendor_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    @property
    def _table_query(self):
        # LEFT JOINs: lines without a container / B/L still appear (empty BL).
        # B/L columns are functionally dependent on b.id (its primary key).
        return SQL("""
            SELECT
                MIN(l.id) AS id,
                SUM(l.product_qty) AS product_qty,
                COUNT(DISTINCT l.container_id) AS container_count,
                STRING_AGG(DISTINCT l.container_id::text, ',') AS container_ids_text,
                b.id AS bill_lading_id,
                l.product_id AS product_id,
                STRING_AGG(DISTINCT COALESCE(r.reference, r.name), ', ') AS requisition_names,
                STRING_AGG(DISTINCT CASE c.container_type
                    WHEN '20' THEN '20ft'
                    WHEN '40' THEN '40ft'
                    WHEN 'other' THEN 'Other'
                END, ', ') AS container_types,
                STRING_AGG(DISTINCT c.invoice_no, ', ') AS invoice_nos,
                COALESCE(b.docs_draft, FALSE) AS docs_draft,
                COALESCE(b.docs_original, FALSE) AS docs_original,
                COALESCE(b.bl_original_release, FALSE) AS bl_original_release,
                COALESCE(b.coo, FALSE) AS coo,
                COALESCE(b.coa, FALSE) AS coa,
                COALESCE(b.hc, FALSE) AS hc,
                COALESCE(b.mtfta, FALSE) AS mtfta,
                b.shipping_line_id AS shipping_line_id,
                b.arrival_date AS arrival_date,
                b.port_of_discharge_id AS port_of_discharge_id,
                l.state AS state,
                l.child_state_id AS child_state_id,
                l.vendor_id AS vendor_id,
                l.company_id AS company_id
            FROM logistics_container_line l
            LEFT JOIN logistics_container c ON c.id = l.container_id
            LEFT JOIN logistics_bill_lading b ON b.id = c.bill_lading_id
            LEFT JOIN purchase_requisition r ON r.id = l.requisition_id
            GROUP BY b.id, l.product_id, l.state, l.child_state_id, l.vendor_id, l.company_id
        """)

    def _read_group_select(self, aggregate_spec, query):
        # Summing per-row counts would count a container once per product;
        # count the distinct ids behind all rows of the group instead.
        if aggregate_spec.startswith('container_count:'):
            ids_text = self._field_to_sql(self._table, 'container_ids_text', query)
            return SQL(
                "(SELECT COUNT(DISTINCT u) FROM unnest(string_to_array(STRING_AGG(%s, ','), ',')) u)",
                ids_text,
            )
        return super()._read_group_select(aggregate_spec, query)

    def action_open_lines(self):
        """Open the container lines aggregated into this report row."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Container Lines',
            'res_model': 'logistics.container.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('bill_lading_id', '=', self.bill_lading_id.id or False),
                ('product_id', '=', self.product_id.id or False),
                ('state', '=', self.state or False),
                ('child_state_id', '=', self.child_state_id.id or False),
                ('vendor_id', '=', self.vendor_id.id or False),
            ],
            'target': 'current',
        }
