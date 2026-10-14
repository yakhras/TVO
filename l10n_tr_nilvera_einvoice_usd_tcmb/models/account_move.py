import logging

from lxml import etree

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

UBL_CAC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
UBL_CBC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_tr_tcmb = fields.Boolean(related='company_id.l10n_tr_tcmb')

    tcmb_rate_type = fields.Selection([
        ('rate', 'Döviz Alış'),
        ('forex_selling_rate', 'Döviz Satış'),
        ('banknote_buying_rate', 'Efektif Alış'),
        ('banknote_selling_rate', 'Efektif Satış'),
    ], string='TCMB Rate Type')

    l10n_tr_tcmb_rate = fields.Float(
        string='TCMB Rate (XML)',
        digits=(16, 4),
        help='Exchange rate from TCMB used for Turkish e-invoice XML generation',
    )

    l10n_tr_tcmb_display_currency_id = fields.Many2one(
        'res.currency',
        string='TCMB Display Currency',
        compute='_compute_tcmb_display_currency',
        help='Currency to display in TCMB rate format (always the non-TRY currency)',
    )

    @api.depends('currency_id', 'company_id.currency_id')
    def _compute_tcmb_display_currency(self):
        """Compute which currency to display in TCMB rate format.

        The rate is always human-readable "TRY per non-TRY currency" (e.g., 44.4).
        Display format: "1 [non-TRY currency] = [rate] TRY"

        Examples:
        - TRY company + USD invoice → "1 USD = 44.4 TRY" (show invoice currency)
        - USD company + TRY invoice → "1 USD = 44.4 TRY" (show company currency)
        - USD company + EUR invoice → "1 EUR = 48.5 TRY" (show invoice currency)
        """
        try_currency = self.env.ref('base.TRY', raise_if_not_found=False)
        for move in self:
            if move.currency_id and move.currency_id != try_currency:
                move.l10n_tr_tcmb_display_currency_id = move.currency_id
            else:
                move.l10n_tr_tcmb_display_currency_id = move.company_id.currency_id



    @api.model
    def _l10n_tr_default_tcmb_rate_type(self, move_type):
        if move_type in ('out_invoice', 'out_refund'):
            return 'banknote_selling_rate'  # Default to 'Efektif Satış'
        if move_type in ('in_invoice', 'in_refund'):
            return 'rate'  # Default to 'Döviz Alış'
        return False

    def _l10n_tr_get_tcmb_rate_values(self, rate_type=None):
        """Look up the TCMB rate of the given type (default: tcmb_rate_type) on the invoice date.

        :returns: (human_rate, currency_rate, is_foreign) where human_rate is "TRY per
                  non-TRY currency" for l10n_tr_tcmb_rate, currency_rate is the raw
                  res.currency.rate value and is_foreign tells if the invoice currency
                  differs from the company currency. (0.0, 0.0, False) when no rate.
        """
        self.ensure_one()
        rate_type = rate_type or self.tcmb_rate_type
        if not rate_type:
            return 0.0, 0.0, False

        try_currency = self.env.ref('base.TRY')
        company_currency = self.company_id.currency_id
        # On a new record's first onchange, currency_id may be computed early by
        # _search_default_journal (before the journal is set) and still be empty
        # here; fall back like account.move._compute_currency_id does.
        invoice_currency = self.currency_id or self.journal_id.currency_id or company_currency
        lookup_currency = try_currency if invoice_currency == company_currency else invoice_currency

        rate_record = self.env['res.currency.rate'].search([
            ('currency_id', '=', lookup_currency.id),
            ('company_id', '=', self.company_id.id),
            ('name', '<=', self.invoice_date or fields.Date.today()),
        ], order='name desc', limit=1)
        rate_value = getattr(rate_record, rate_type, 0.0) if rate_record else 0.0
        if not rate_value:
            return 0.0, 0.0, False

        human_rate = rate_value if lookup_currency == try_currency else round(1.0 / rate_value, 10)
        return human_rate, rate_value, invoice_currency != company_currency

    def _l10n_tr_get_rate_from_xml(self, attachments=None):
        """Read the rate from the Nilvera UBL XML of the move (the rate GİB received).

        :returns: None when there is no XML or it has no PricingExchangeRate (nothing was
                  sent, the caller may use the TCMB table), 0.0 when the XML rate can't be
                  mapped to "TRY per non-TRY currency", else that rate.
        """
        self.ensure_one()
        xml_mimetypes = ('application/xml', 'text/xml')
        xml_attachments = (attachments or self.env['ir.attachment']).filtered(
            lambda a: a.mimetype in xml_mimetypes)
        if not xml_attachments:
            xml_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', self.id),
                ('mimetype', 'in', xml_mimetypes),
            ], order='id desc')

        for attachment in xml_attachments:
            try:
                tree = etree.fromstring(attachment.raw)
            except (etree.XMLSyntaxError, ValueError, TypeError):
                continue
            node = tree.find('.//{%s}PricingExchangeRate' % UBL_CAC)
            if node is None:
                return None
            source = (node.findtext('{%s}SourceCurrencyCode' % UBL_CBC) or '').strip().upper()
            target = (node.findtext('{%s}TargetCurrencyCode' % UBL_CBC) or '').strip().upper()
            try:
                rate = float(node.findtext('{%s}CalculationRate' % UBL_CBC) or 0.0)
            except ValueError:
                return 0.0
            # A rate of 1 between two different currencies is a placeholder, not a rate.
            if not rate or source == target or rate == 1.0:
                return 0.0
            if target == 'TRY':
                return rate
            if source == 'TRY':
                return round(1.0 / rate, 10)
            return 0.0
        return None

    def _l10n_tr_fill_tcmb_rate(self, attachments=None):
        """Fill l10n_tr_tcmb_rate on invoices that have none, without touching the accounting.

        Rates typed by hand (non-zero) are never overwritten. Sales documents already
        sent/received through Nilvera keep the rate of their XML; the others get the
        TCMB table rate. invoice_currency_rate is never written, so posted moves don't
        need to be re-posted.

        :returns: the moves that could not be filled.
        """
        skipped = self.browse()
        for move in self:
            if not move.is_invoice(include_receipts=True) or not move.l10n_tr_tcmb or move.l10n_tr_tcmb_rate:
                continue
            vals = {}
            rate = None
            if move.is_sale_document(include_receipts=True) and move.l10n_tr_nilvera_send_status == 'succeed':
                rate = move._l10n_tr_get_rate_from_xml(attachments)
            if rate is None:
                rate_type = move.tcmb_rate_type or move._l10n_tr_default_tcmb_rate_type(move.move_type)
                rate = move._l10n_tr_get_tcmb_rate_values(rate_type)[0]
                if rate and not move.tcmb_rate_type:
                    vals['tcmb_rate_type'] = rate_type
            if not rate:
                skipped |= move
                continue
            vals['l10n_tr_tcmb_rate'] = rate
            move.write(vals)
        return skipped

    def _extend_with_attachments(self, attachments, new=False):
        # Runs after the EDI import (Nilvera sync, upload, mail alias) has set the
        # currency and the invoice date, and before _autopost_bill.
        res = super()._extend_with_attachments(attachments, new=new)
        moves = self | self.browse(attachments.filtered(lambda a: a.res_model == self._name).mapped('res_id'))
        moves.exists()._l10n_tr_fill_tcmb_rate(attachments)
        return res

    @api.onchange('tcmb_rate_type', 'currency_id', 'invoice_date')
    def _onchange_tcmb_rate_type(self):
        """Update l10n_tr_tcmb_rate based on selected TCMB rate type."""
        if not self.is_invoice(include_receipts=True) or not self.tcmb_rate_type or not self.l10n_tr_tcmb:
            return

        human_rate, rate_value, is_foreign = self._l10n_tr_get_tcmb_rate_values()
        if not human_rate:
            return

        self.l10n_tr_tcmb_rate = human_rate
        if is_foreign:
            self.invoice_currency_rate = rate_value

    @api.onchange('l10n_tr_tcmb_rate')
    def _onchange_l10n_tr_tcmb_rate(self):
        if not self.l10n_tr_tcmb or not self.l10n_tr_tcmb_rate or self.currency_id == self.company_id.currency_id:
            return
        
        if self.currency_id.name == 'TRY':
            self.invoice_currency_rate = self.l10n_tr_tcmb_rate
        else:
            self.invoice_currency_rate = round(1.0 / self.l10n_tr_tcmb_rate, 10)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'tcmb_rate_type' in fields_list and self.env.company.l10n_tr_tcmb:
            rate_type = self._l10n_tr_default_tcmb_rate_type(self._context.get('default_move_type'))
            if rate_type:
                res['tcmb_rate_type'] = rate_type
        return res
