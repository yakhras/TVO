from odoo import fields, models
from odoo.tools.sql import SQL

from .logistics_container import CONTAINER_STATE_SELECTION


def _arrival_report_query(dimensions):
    """One row per unique combination of `dimensions` (container line columns),
    with summed quantities and a distinct container count."""
    dims = SQL(", ").join(SQL.identifier("l", dim) for dim in dimensions)
    return SQL("""
        SELECT
            MIN(l.id) AS id,
            %(dims)s,
            l.company_id AS company_id,
            SUM(l.product_qty) AS product_qty,
            SUM(l.total_weight) AS total_weight,
            COUNT(DISTINCT l.container_id) AS container_count
        FROM logistics_container_line l
        GROUP BY %(dims)s, l.company_id
    """, dims=dims)


def _action_open_lines(report):
    """Open the container lines aggregated into this report row."""
    report.ensure_one()
    domain = [('company_id', '=', report.company_id.id)]
    for dim in report._dimensions:
        value = report[dim]
        if isinstance(value, models.BaseModel):
            value = value.id
        domain.append((dim, '=', value or False))
    return {
        'type': 'ir.actions.act_window',
        'name': 'Container Lines',
        'res_model': 'logistics.container.line',
        'view_mode': 'list,form',
        'views': [(False, 'list'), (False, 'form')],
        'domain': domain,
        'target': 'current',
    }


class LogisticsArrivalProductReport(models.Model):
    _name = 'logistics.arrival.product.report'
    _description = 'Arrivals by Product'
    _auto = False
    _order = 'arrival_date desc, product_id'

    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement', readonly=True)
    arrival_date = fields.Date(string='Arriving Date', readonly=True)
    port_of_discharge_id = fields.Many2one('logistics.port', string='Port To', readonly=True)
    dest_city_id = fields.Many2one('res.country.state', string='Destination City', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    description_picking = fields.Text(string='Description on Picking', readonly=True)
    product_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', readonly=True)
    total_weight = fields.Float(string='Total Weight', digits='Stock Weight', readonly=True)
    container_count = fields.Integer(string='Number of Containers', readonly=True)
    state = fields.Selection(CONTAINER_STATE_SELECTION, string='Status', readonly=True)
    child_state_id = fields.Many2one(
        'logistics.container.child.state', string='Child State', readonly=True,
    )
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    _dimensions = [
        'requisition_id', 'arrival_date', 'port_of_discharge_id', 'dest_city_id',
        'product_id', 'description_picking', 'state', 'child_state_id',
    ]

    @property
    def _table_query(self):
        return _arrival_report_query(self._dimensions)

    def action_open_lines(self):
        return _action_open_lines(self)


class LogisticsCargoReadinessReport(models.Model):
    """Restricted to the Purchasing state by the action domain; child states are
    picked in the search panel."""
    _name = 'logistics.cargo.readiness.report'
    _description = 'Cargo Readiness'
    _auto = False
    _order = 'readiness_date, requisition_id'

    requisition_id = fields.Many2one('purchase.requisition', string='Contract No', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    readiness_date = fields.Date(string='Cargo Readiness Date', readonly=True)
    eeta_date = fields.Date(string='EETA', readonly=True)
    container_type = fields.Selection(
        selection=[('20', '20ft'), ('40', '40ft'), ('other', 'Other')],
        string='Container Type', readonly=True,
    )
    container_count = fields.Integer(string='Total Containers', readonly=True)
    # Port From comes from the B/L, so it stays empty until one is linked.
    port_of_loading_id = fields.Many2one('logistics.port', string='Loading Port', readonly=True)
    vendor_id = fields.Many2one('res.partner', string='Supplier', readonly=True)
    product_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', readonly=True)
    total_weight = fields.Float(string='Total Weight', digits='Stock Weight', readonly=True)
    state = fields.Selection(CONTAINER_STATE_SELECTION, string='Status', readonly=True)
    child_state_id = fields.Many2one(
        'logistics.container.child.state', string='Child State', readonly=True,
    )
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    _dimensions = [
        'readiness_date', 'eeta_date', 'requisition_id', 'product_id', 'container_type',
        'port_of_loading_id', 'vendor_id', 'state', 'child_state_id',
    ]

    @property
    def _table_query(self):
        return _arrival_report_query(self._dimensions)

    def action_open_lines(self):
        return _action_open_lines(self)


class LogisticsArrivalForwarderReport(models.Model):
    _name = 'logistics.arrival.forwarder.report'
    _description = 'Arrivals by Forwarder'
    _auto = False
    _order = 'arrival_date desc, forwarder_id, requisition_id, bill_lading_id, product_id'

    arrival_date = fields.Date(string='Arriving Date', readonly=True)
    port_of_discharge_id = fields.Many2one('logistics.port', string='Port To', readonly=True)
    dest_city_id = fields.Many2one('res.country.state', string='Destination City', readonly=True)
    forwarder_id = fields.Many2one('res.partner', string='Forwarder', readonly=True)
    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement', readonly=True)
    bill_lading_id = fields.Many2one('logistics.bill.lading', string='Bill of Lading', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    description_picking = fields.Text(string='Description on Picking', readonly=True)
    product_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', readonly=True)
    total_weight = fields.Float(string='Total Weight', digits='Stock Weight', readonly=True)
    container_count = fields.Integer(string='Number of Containers', readonly=True)
    state = fields.Selection(CONTAINER_STATE_SELECTION, string='Status', readonly=True)
    child_state_id = fields.Many2one(
        'logistics.container.child.state', string='Child State', readonly=True,
    )
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    _dimensions = [
        'arrival_date', 'port_of_discharge_id', 'dest_city_id', 'forwarder_id',
        'requisition_id', 'bill_lading_id', 'product_id', 'description_picking',
        'state', 'child_state_id',
    ]

    @property
    def _table_query(self):
        return _arrival_report_query(self._dimensions)

    def action_open_lines(self):
        return _action_open_lines(self)
