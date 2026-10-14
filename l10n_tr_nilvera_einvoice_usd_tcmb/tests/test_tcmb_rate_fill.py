from odoo import fields
from odoo.tests import tagged

from .common import TcmbRateCommon

UBL_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cac:PricingExchangeRate>
    <cbc:SourceCurrencyCode>%s</cbc:SourceCurrencyCode>
    <cbc:TargetCurrencyCode>%s</cbc:TargetCurrencyCode>
    <cbc:CalculationRate>%s</cbc:CalculationRate>
  </cac:PricingExchangeRate>
</Invoice>"""


@tagged('post_install', '-at_install')
class TestTcmbRateFill(TcmbRateCommon):

    def _invoice(self, move_type, post=True, currency=None, invoice_date=None, **vals):
        move = self.init_invoice(
            move_type,
            invoice_date=invoice_date or self.rate_date,
            amounts=[1000.0],
            post=post,
            currency=currency,
        )
        # Simulate an old record: no TCMB rate stored.
        move.write({'l10n_tr_tcmb_rate': 0.0, **vals})
        return move

    def _attach_xml(self, move, source, target, rate):
        return self.env['ir.attachment'].create({
            'name': 'nilvera.xml',
            'raw': UBL_XML % (source.encode(), target.encode(), rate.encode()),
            'mimetype': 'application/xml',
            'res_model': 'account.move',
            'res_id': move.id,
        })

    def _accounting_snapshot(self, move):
        return (
            move.invoice_currency_rate,
            [(line.debit, line.credit, line.balance, line.amount_currency) for line in move.line_ids.sorted('id')],
        )

    def test_fill_posted_bill_keeps_accounting(self):
        bill = self._invoice('in_invoice', tcmb_rate_type='rate')
        self.assertEqual(bill.state, 'posted')
        before = self._accounting_snapshot(bill)

        skipped = bill._l10n_tr_fill_tcmb_rate()

        self.assertFalse(skipped)
        self.assertAlmostEqual(bill.l10n_tr_tcmb_rate, self.rates['rate'], places=4)
        self.assertEqual(self._accounting_snapshot(bill), before)
        self.assertEqual(bill.state, 'posted')

    def test_fill_sets_missing_rate_type(self):
        invoice = self._invoice('out_invoice', tcmb_rate_type=False)
        invoice._l10n_tr_fill_tcmb_rate()
        self.assertEqual(invoice.tcmb_rate_type, 'banknote_selling_rate')
        self.assertAlmostEqual(invoice.l10n_tr_tcmb_rate, self.rates['banknote_selling_rate'], places=4)

    def test_typed_rate_never_overwritten(self):
        bill = self._invoice('in_invoice', post=False, l10n_tr_tcmb_rate=45.5)
        bill._l10n_tr_fill_tcmb_rate()
        bill._extend_with_attachments(self.env['ir.attachment'], new=False)
        self.assertAlmostEqual(bill.l10n_tr_tcmb_rate, 45.5, places=4)

    def test_fill_skips_without_rate_data(self):
        bill = self._invoice('in_invoice', invoice_date=fields.Date.to_date('2000-01-03'), tcmb_rate_type='rate')
        skipped = bill._l10n_tr_fill_tcmb_rate()
        self.assertEqual(skipped, bill)
        self.assertFalse(bill.l10n_tr_tcmb_rate)

    def test_sent_invoice_rate_from_xml(self):
        invoice = self._invoice('out_invoice', l10n_tr_nilvera_send_status='succeed', tcmb_rate_type='banknote_selling_rate')
        self._attach_xml(invoice, 'USD', 'TRY', '41.1234')
        invoice._l10n_tr_fill_tcmb_rate()
        # The rate GİB received wins over the TCMB table value.
        self.assertAlmostEqual(invoice.l10n_tr_tcmb_rate, 41.1234, places=4)

    def test_sent_try_invoice_rate_from_xml_inverted(self):
        invoice = self._invoice('out_invoice', currency=self.try_currency, l10n_tr_nilvera_send_status='succeed')
        self._attach_xml(invoice, 'TRY', 'USD', '0.020355')
        invoice._l10n_tr_fill_tcmb_rate()
        self.assertAlmostEqual(invoice.l10n_tr_tcmb_rate, round(1 / 0.020355, 4), places=4)

    def test_sent_invoice_placeholder_xml_rate_skipped(self):
        invoice = self._invoice('out_invoice', currency=self.try_currency, l10n_tr_nilvera_send_status='succeed')
        self._attach_xml(invoice, 'TRY', 'USD', '1')
        skipped = invoice._l10n_tr_fill_tcmb_rate()
        self.assertEqual(skipped, invoice)
        self.assertFalse(invoice.l10n_tr_tcmb_rate)

    def test_sent_invoice_without_xml_rate_uses_table(self):
        invoice = self._invoice('out_invoice', l10n_tr_nilvera_send_status='succeed', tcmb_rate_type='banknote_selling_rate')
        self.env['ir.attachment'].create({
            'name': 'nilvera.xml',
            'raw': b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>',
            'mimetype': 'application/xml',
            'res_model': 'account.move',
            'res_id': invoice.id,
        })
        invoice._l10n_tr_fill_tcmb_rate()
        self.assertAlmostEqual(invoice.l10n_tr_tcmb_rate, self.rates['banknote_selling_rate'], places=4)

    def test_import_hook_fills_rate(self):
        # Same state as a bill right after the Nilvera UBL import: currency and date
        # set, rate type defaulted, no rate (onchanges don't run on create()).
        bill = self.env['account.move'].with_context(default_move_type='in_invoice').create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': self.rate_date,
        })
        self.assertEqual(bill.tcmb_rate_type, 'rate')
        self.assertFalse(bill.l10n_tr_tcmb_rate)

        bill._extend_with_attachments(self.env['ir.attachment'], new=True)

        self.assertAlmostEqual(bill.l10n_tr_tcmb_rate, self.rates['rate'], places=4)
