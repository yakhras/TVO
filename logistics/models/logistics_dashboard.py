from odoo import api, fields, models


class LogisticsDashboard(models.AbstractModel):
    _name = 'logistics.dashboard'
    _description = 'Logistics Dashboard'

    @api.model
    def get_dashboard_data(self):
        Req = self.env['purchase.requisition'].sudo()
        Container = self.env['logistics.container'].sudo()
        Line = self.env['logistics.container.line'].sudo()
        BL = self.env['logistics.bill.lading'].sudo()

        deals_by_state = {
            state: Req.search_count([('state', '=', state)])
            for state in ('draft', 'confirmed', 'done', 'cancel')
        }

        containers_by_state = {
            state: Container.search_count([('state', '=', state)])
            for state in ('purchase', 'oversea', 'at_port', 'arrived', 'antrepo')
        }

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
                'containers_purchase': containers_by_state['purchase'],
                'containers_oversea': containers_by_state['oversea'],
                'containers_at_port': containers_by_state['at_port'],
                'containers_arrived': containers_by_state['arrived'],
                'containers_antrepo': containers_by_state['antrepo'],
                'bl_docs_pending': bl_docs_pending,
                'bl_docs_draft': bl_docs_draft,
                'bl_docs_original': bl_docs_original,
            },
            'upcoming_arrivals': upcoming.read([
                'requisition_id', 'vendor_id', 'product_id', 'product_qty',
                'sku_price', 'total_weight', 'subtotal', 'container_id',
                'bill_lading_id', 'mt_price', 'arrival_date', 'currency_id',
            ]),
        }
