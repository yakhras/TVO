from odoo import api, fields, models


class LogisticsDashboard(models.AbstractModel):
    _name = 'logistics.dashboard'
    _description = 'Logistics Dashboard'

    @api.model
    def get_dashboard_data(self):
        Req = self.env['purchase.requisition'].sudo()
        Line = self.env['logistics.container.line'].sudo()

        deals_by_state = {
            state: Req.search_count([('state', '=', state)])
            for state in ('draft', 'confirmed', 'done', 'cancel')
        }

        upcoming = Line.search([
            ('state', 'not in', ['arrived', 'antrepo']),
            ('arrival_date', '!=', False),
        ], order='arrival_date desc', limit=10)

        return {
            'kpis': {
                'deals_draft': deals_by_state['draft'],
                'deals_confirmed': deals_by_state['confirmed'],
                'deals_closed': deals_by_state['done'],
                'deals_cancelled': deals_by_state['cancel'],
            },
            'upcoming_arrivals': upcoming.read([
                'requisition_id', 'vendor_id', 'product_id', 'product_qty',
                'sku_price', 'total_weight', 'subtotal', 'container_id',
                'bill_lading_id', 'mt_price', 'arrival_date', 'currency_id',
            ]),
        }
