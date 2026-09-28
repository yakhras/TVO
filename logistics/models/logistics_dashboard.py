from odoo import api, fields, models

from .logistics_container_child_state import CONTAINER_STATE_SELECTION


class LogisticsDashboard(models.AbstractModel):
    _name = 'logistics.dashboard'
    _description = 'Logistics Dashboard'

    _UPCOMING_ARRIVAL_DOMAIN = [
        ('state', 'not in', ['arrived', 'antrepo']),
        ('arrival_date', '!=', False),
    ]
    _UPCOMING_ARRIVAL_FIELDS = [
        'requisition_id', 'vendor_id', 'product_id', 'product_qty',
        'sku_price', 'total_weight', 'subtotal', 'container_id',
        'bill_lading_id', 'mt_price', 'arrival_date', 'currency_id',
    ]
    _UPCOMING_ARRIVAL_PAGE_SIZE = 10

    @api.model
    def get_upcoming_arrivals(self, offset=0, limit=_UPCOMING_ARRIVAL_PAGE_SIZE):
        Line = self.env['logistics.container.line'].sudo()
        lines = Line.search(
            self._UPCOMING_ARRIVAL_DOMAIN, order='arrival_date asc',
            offset=offset, limit=limit,
        )
        total = Line.search_count(self._UPCOMING_ARRIVAL_DOMAIN)
        return {
            'lines': lines.read(self._UPCOMING_ARRIVAL_FIELDS),
            'has_more': offset + len(lines) < total,
        }

    @api.model
    def get_dashboard_data(self):
        Req = self.env['purchase.requisition'].sudo()
        Container = self.env['logistics.container'].sudo()
        BL = self.env['logistics.bill.lading'].sudo()

        deals_by_state = {
            state: Req.search_count([('state', '=', state)])
            for state in ('draft', 'confirmed', 'done', 'cancel')
        }

        containers_by_state = {
            state: Container.search_count([('state', '=', state)])
            for state, _label in CONTAINER_STATE_SELECTION
        }

        counts_by_child = {
            child_state.id: count
            for child_state, count in Container._read_group(
                [], ['child_state_id'], ['__count'])
        }
        child_states = self.env['logistics.container.child.state'].sudo().search([])
        container_states = [{
            'state': state,
            'label': label,
            'count': containers_by_state[state],
            'children': [{
                'id': c.id,
                'name': c.child_state,
                'count': counts_by_child.get(c.id, 0),
            } for c in child_states.filtered(lambda c: c.parent_state == state)],
        } for state, label in CONTAINER_STATE_SELECTION]

        bl_has_number = [('number', '!=', False), ('number', '!=', '')]
        bl_docs_pending = BL.search_count(bl_has_number + [
            ('docs_draft', '=', False), ('docs_original', '=', False),
        ])
        bl_docs_draft = BL.search_count(bl_has_number + [
            ('docs_draft', '=', True), ('docs_original', '=', False),
        ])
        bl_docs_original = BL.search_count(bl_has_number + [
            ('docs_draft', '=', True), ('docs_original', '=', True),
        ])

        upcoming = self.get_upcoming_arrivals(offset=0, limit=self._UPCOMING_ARRIVAL_PAGE_SIZE)

        return {
            'kpis': {
                'deals_draft': deals_by_state['draft'],
                'deals_confirmed': deals_by_state['confirmed'],
                'deals_closed': deals_by_state['done'],
                'deals_cancelled': deals_by_state['cancel'],
                'bl_docs_pending': bl_docs_pending,
                'bl_docs_draft': bl_docs_draft,
                'bl_docs_original': bl_docs_original,
            },
            'container_states': container_states,
            'upcoming_arrivals': upcoming['lines'],
            'upcoming_arrivals_has_more': upcoming['has_more'],
        }
