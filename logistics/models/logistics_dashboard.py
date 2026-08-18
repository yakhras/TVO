from odoo import api, fields, models


class LogisticsDashboard(models.AbstractModel):
    _name = 'logistics.dashboard'
    _description = 'Logistics Dashboard'

    @api.model
    def get_dashboard_data(self):
        BL = self.env['logistics.bill.lading'].sudo()
        Req = self.env['purchase.requisition'].sudo()

        deals_by_state = {
            state: Req.search_count([('state', '=', state)])
            for state in ('draft', 'confirmed', 'done', 'cancel')
        }

        upcoming = BL.search([
            ('state', 'in', ['shipped', 'in_transit']),
            ('arrival_date', '!=', False),
        ], order='arrival_date asc', limit=10)

        return {
            'kpis': {
                'deals_draft': deals_by_state['draft'],
                'deals_confirmed': deals_by_state['confirmed'],
                'deals_closed': deals_by_state['done'],
                'deals_cancelled': deals_by_state['cancel'],
            },
            'upcoming_arrivals': upcoming.read(
                ['name', 'number', 'vessel', 'arrival_date',
                 'container_count', 'forwarder_id', 'port_of_discharge_id']
            ),
        }
