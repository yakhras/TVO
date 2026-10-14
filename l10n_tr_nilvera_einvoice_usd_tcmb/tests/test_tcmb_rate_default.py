from odoo.tests import Form, tagged

from .common import TcmbRateCommon


@tagged('post_install', '-at_install')
class TestTcmbRateDefault(TcmbRateCommon):

    def _new_move_form(self, move_type):
        return Form(self.env['account.move'].with_context(default_move_type=move_type))

    def test_company_currency_is_not_try(self):
        # The lookup below assumes a non-TRY company currency (USD in TVO).
        self.assertNotEqual(self.company.currency_id, self.try_currency)

    def test_out_invoice_default_rate_rendered(self):
        """Regression: the default rate type must fill the rate without touching the form."""
        move_form = self._new_move_form('out_invoice')
        self.assertEqual(move_form.tcmb_rate_type, 'banknote_selling_rate')
        self.assertAlmostEqual(move_form.l10n_tr_tcmb_rate, self.rates['banknote_selling_rate'], places=4)

    def test_in_invoice_default_rate_rendered(self):
        move_form = self._new_move_form('in_invoice')
        self.assertEqual(move_form.tcmb_rate_type, 'rate')
        self.assertAlmostEqual(move_form.l10n_tr_tcmb_rate, self.rates['rate'], places=4)

    def test_refunds_default_rate_rendered(self):
        for move_type, rate_type in (('out_refund', 'banknote_selling_rate'), ('in_refund', 'rate')):
            with self.subTest(move_type=move_type):
                move_form = self._new_move_form(move_type)
                self.assertEqual(move_form.tcmb_rate_type, rate_type)
                self.assertAlmostEqual(move_form.l10n_tr_tcmb_rate, self.rates[rate_type], places=4)

    def test_change_rate_type_updates_rate(self):
        move_form = self._new_move_form('out_invoice')
        move_form.tcmb_rate_type = 'forex_selling_rate'
        self.assertAlmostEqual(move_form.l10n_tr_tcmb_rate, self.rates['forex_selling_rate'], places=4)

    def test_tcmb_disabled_no_default(self):
        self.company.l10n_tr_tcmb = False
        move_form = self._new_move_form('out_invoice')
        self.assertFalse(move_form.tcmb_rate_type)
        self.assertFalse(move_form.l10n_tr_tcmb_rate)
