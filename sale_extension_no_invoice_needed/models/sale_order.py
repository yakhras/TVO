# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    invoice_status = fields.Selection(
        selection_add=[('no_invoice_needed', 'No Invoice Needed')],
        ondelete={'no_invoice_needed': 'set null'})

    # Flag that forces invoice_status to 'no_invoice_needed'
    no_invoice_needed = fields.Boolean(string="No Invoice Needed", copy=False)

    # v18 name of v15's _get_invoice_status; depends are merged with core ('state', 'order_line.invoice_status')
    @api.depends('no_invoice_needed')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        for order in self:
            if order.no_invoice_needed and order.state == 'sale':
                order.invoice_status = 'no_invoice_needed'

    # Header button on 'Orders to Invoice' list
    def action_set_no_invoice_needed(self):
        orders = self.filtered(lambda o: o.invoice_status == 'to invoice')
        orders.no_invoice_needed = True
        for order in orders:
            order.message_post(body=_("Invoice status changed from 'To Invoice' to 'No Invoice Needed'."))

    # Header button on 'No Invoice Needed' list
    def action_reset_to_invoice(self):
        orders = self.filtered(lambda o: o.invoice_status == 'no_invoice_needed')
        orders.no_invoice_needed = False
        for order in orders:
            order.message_post(body=_("Invoice status changed from 'No Invoice Needed' to 'To Invoice'."))
