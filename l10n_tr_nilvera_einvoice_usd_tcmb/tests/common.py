from datetime import timedelta

from odoo import fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TcmbRateCommon(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.l10n_tr_tcmb = True
        cls.try_currency = cls.env.ref('base.TRY')
        cls.try_currency.active = True
        cls.rate_date = fields.Date.today() - timedelta(days=1)
        cls.rates = {
            'rate': 49.2794,
            'forex_selling_rate': 49.3681,
            'banknote_buying_rate': 49.2449,
            'banknote_selling_rate': 49.4422,
        }
        cls.env['res.currency.rate'].create({
            'currency_id': cls.try_currency.id,
            'company_id': cls.company.id,
            'name': cls.rate_date,
            **cls.rates,
        })
