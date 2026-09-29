# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.tools import float_round
from odoo import tools


from ..constants import ReportConstants


class AccountMoveLineReport(models.Model):
    _name = 'account.move.line.report'
    _description = 'Account Move Line Report'
    _auto = False
    _order = 'date asc, reference asc, line_sort asc, id asc'

    date = fields.Date(string='Date', readonly=True)
    move_id = fields.Many2one('account.move', string='Reference', readonly=True)
    amount_currency = fields.Monetary(string='Amount Currency', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Original Currency', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    tr_currency_id = fields.Many2one('res.currency', string='TRY Currency', compute='_compute_tr_currency_id')
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)

    # Enhance dta view
    reference = fields.Char(string="Reference", readonly=True)
    note = fields.Char(string="Note", readonly=True)
    type_key = fields.Char(string='Type Key', readonly=True)
    type = fields.Char(string='Type', compute='_compute_type_display', store=False)

    # For Normal Report in Company Currency
    debit = fields.Monetary(string='Debit', readonly=True, currency_field='company_currency_id')
    credit = fields.Monetary(string='Credit', readonly=True, currency_field='company_currency_id')
    balance = fields.Monetary(string='Balance', readonly=True)
    cumulated_balance = fields.Monetary(string='Cumulated Balance', compute='_compute_cumulated_balance', store=False, currency_field='company_currency_id')

    # For TRY Value Report
    tr_rate_display = fields.Char('Rate', compute='_compute_amount_tr_currency')
    amount_tr_currency = fields.Monetary('TL Value', compute='_compute_amount_tr_currency', currency_field='tr_currency_id')
    cumulated_amount_tr_currency = fields.Monetary('Cumulated TL', compute='_compute_cumulated_amount_tr_currency', currency_field='tr_currency_id')
    amount_tr_debit = fields.Monetary(string='Debit', compute='_compute_amount_tr_debit_credit', currency_field='tr_currency_id', store=False)
    amount_tr_credit = fields.Monetary(string='Credit', compute='_compute_amount_tr_debit_credit', currency_field='tr_currency_id', store=False)

    # Line classification
    line_type = fields.Selection(
        [('summary', 'Summary'), ('product', 'Product')],
        string='Line Type', readonly=True
    )
    line_sort = fields.Integer(string='Line Sort', readonly=True)

    # Product detail fields
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True)
    price_unit = fields.Float(string='Unit Price', readonly=True)
    discount = fields.Float(string='Discount (%)', readonly=True)
    price_subtotal = fields.Monetary(string='Subtotal', readonly=True, currency_field='currency_id')
    price_total = fields.Monetary(string='Total', readonly=True, currency_field='currency_id')
    tax_amount = fields.Monetary(string='Tax', readonly=True, currency_field='currency_id')
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_cumulation_sort_key(self, record):
        """Standard sort key for cumulation calculations."""
        return (
            record.partner_id.id or 0,
            record.date or '',
            record.reference or '',
            record.line_sort or 0,
            record.id
        )

    def _cumulate_by_group(self, value_field, result_field, initial_values):
        """Shared accumulation pattern for cumulated balance fields.

        Args:
            value_field: Name of the field to read incremental values from.
            result_field: Name of the field to write cumulated values to.
            initial_values: Dict mapping partner_id -> initial balance float.
        """
        grouped = {}
        for rec in sorted(self, key=self._get_cumulation_sort_key):
            if rec.line_type == 'product':
                rec[result_field] = 0.0
                continue
            pid = rec.partner_id.id
            if pid not in grouped:
                grouped[pid] = initial_values.get(pid, 0.0)
            grouped[pid] += rec[value_field] or 0.0
            rec[result_field] = grouped[pid]

    def _fetch_initial_balances_sql(self):
        """Fetch initial balances using raw SQL (for stored debit/credit fields).

        Returns:
            Dict mapping partner_id -> initial balance float.
        """
        # Skip if skip_opening is set in context
        if self.env.context.get('skip_opening'):
            return {}

        date_from = self.env.context.get('date_from')
        if not date_from or not self:
            return {}
        partners = self.mapped('partner_id')
        if not partners:
            return {}
        self.env.cr.execute("""
            SELECT amlr.partner_id, SUM(amlr.debit) - SUM(amlr.credit)
            FROM account_move_line_report amlr
            JOIN account_move am ON am.id = amlr.move_id
            JOIN account_journal aj ON aj.id = am.journal_id
            WHERE amlr.date < %s
            AND amlr.partner_id IN %s
            AND amlr.line_type = 'summary'
            AND amlr.company_id = ANY(%s)
            AND aj.code NOT IN %s
            GROUP BY amlr.partner_id
        """, (date_from, tuple(partners.ids), list(self.env.companies.ids), ReportConstants.EXCLUDED_JOURNAL_CODES))
        return dict(self.env.cr.fetchall())

    def _fetch_initial_tr_balances(self):
        """Fetch initial TRY balances using ORM (for computed amount_tr_currency).

        Returns:
            Dict mapping partner_id -> initial TRY balance float.
        """
        # Skip if skip_opening is set in context
        if self.env.context.get('skip_opening'):
            return {}

        date_from = self.env.context.get('date_from')
        if not date_from or not self:
            return {}
        partners = self.mapped('partner_id')
        if not partners:
            return {}
        prior_records = self.search([
            ('date', '<', date_from),
            ('partner_id', 'in', partners.ids),
            ('line_type', '=', 'summary'),
            ('company_id', 'in', self.env.companies.ids),
            ('move_id.journal_id.code', 'not in', ReportConstants.EXCLUDED_JOURNAL_CODES),
        ])
        initial_balances = {}
        for rec in prior_records:
            pid = rec.partner_id.id
            initial_balances[pid] = initial_balances.get(pid, 0.0) + (rec.amount_tr_currency or 0.0)
        return initial_balances

    def _zero_product_fields(self, *field_names):
        """Zero out specified fields for all product-type records in self.

        Returns:
            Recordset of non-product records that still need processing.
        """
        product_recs = self.filtered(lambda r: r.line_type == 'product')
        for rec in product_recs:
            for fname in field_names:
                rec[fname] = 0.0 if self._fields[fname].type != 'char' else ""
        return self - product_recs

    def _get_try_currency(self):
        """Return the TRY res.currency record (cached per-environment)."""
        if not hasattr(self.env, '_try_currency_cache'):
            self.env._try_currency_cache = self.env['res.currency'].search(
                [('name', '=', ReportConstants.CURRENCY_TRY)], limit=1
            )
        return self.env._try_currency_cache

    def get_product_lines(self):
        """Product lines of these report rows' invoices, for the list view's
        "Products" sub-tables.

        The report spans all companies, but a plain client-side searchRead on
        account.move.line is restricted to the browser's active companies, so
        invoices of other companies showed no products on screen while the
        (sudo) PDF/XLSX exports did. Access is checked on the report rows
        themselves, then the lines are read with sudo like the exports.
        """
        self.check_access('read')
        return self.env['account.move.line'].sudo().search_read(
            [('move_id', 'in', self.move_id.ids), ('display_type', '=', 'product')],
            ['move_id', 'product_id', 'quantity', 'product_uom_id', 'price_unit',
             'discount', 'price_total', 'price_subtotal'],
        )

    def _compute_tr_currency_id(self):
        """Always return TRY currency for monetary field formatting."""
        try_currency = self._get_try_currency()
        for rec in self:
            rec.tr_currency_id = try_currency

    # -------------------------------------------------------------------------
    # Database View
    # -------------------------------------------------------------------------

    def init(self):
        """Initialize the report view"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW account_move_line_report AS (
                WITH check_aggregates AS (
                    SELECT ap.id as payment_id,
                        string_agg(DISTINCT ac.name::text, ', ' ORDER BY ac.name::text) as check_numbers
                    FROM account_payment ap
                    JOIN account_cheque ac ON ac.payment_id = ap.id
                    GROUP BY ap.id
                )

                -- Summary lines (receivable/payable) — existing
                SELECT
                    aml.id, aml.date, aml.move_id, aml.partner_id, aml.account_id, aml.company_id,
                    aml.debit, aml.credit, aml.balance,
                    aml.amount_currency, aml.currency_id, rc.id AS company_currency_id,
                    CASE
                        WHEN aj.type = 'cash' AND ca.check_numbers IS NOT NULL THEN
                            ca.check_numbers
                        WHEN aj.type = 'bank' AND aml.ref IS NOT NULL THEN
                            aml.ref
                        ELSE
                            am.name
                    END AS reference,

                    CASE
                        WHEN am.move_type = 'out_invoice' THEN 'out_invoice'
                        WHEN am.move_type = 'in_invoice' THEN 'in_invoice'
                        WHEN am.move_type = 'out_refund' THEN 'out_refund'
                        WHEN am.move_type = 'in_refund' THEN 'in_refund'
                        WHEN aj.type = 'bank' THEN 'bank_payment'
                        WHEN aj.type = 'cash' AND ca.check_numbers IS NOT NULL THEN 'check_payment'
                        WHEN aj.type = 'cash' AND ca.check_numbers IS NULL THEN 'manual_payment'
                        WHEN aj.type = 'purchase' THEN 'purchase'
                        WHEN aj.type = 'sale' THEN 'sale'
                        ELSE 'journal_entry'
                    END AS type_key,
                    aml.name AS note,
                    NULL::integer AS product_id,
                    NULL::integer AS product_uom_id,
                    NULL::numeric AS quantity,
                    NULL::numeric AS price_unit,
                    NULL::numeric AS discount,
                    NULL::numeric AS price_subtotal,
                    NULL::numeric AS price_total,
                    NULL::numeric AS tax_amount,
                    0 AS line_sort,
                    'summary' AS line_type
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN account_journal aj ON aj.id = am.journal_id
                JOIN account_account aa ON aa.id = aml.account_id
                JOIN res_company comp ON comp.id = aml.company_id
                JOIN res_currency rc ON rc.id = comp.currency_id
                LEFT JOIN account_payment ap ON ap.move_id = am.id
                LEFT JOIN check_aggregates ca ON ca.payment_id = ap.id
                WHERE am.state = 'posted'
                AND aa.account_type IN ('asset_receivable', 'liability_payable')
                AND aml.partner_id IS NOT NULL

                UNION ALL

                -- Product detail lines (from invoices/bills)
                SELECT
                    aml.id AS id,
                    am.date AS date,
                    aml.move_id AS move_id,
                    aml.partner_id AS partner_id,
                    aml.account_id AS account_id,
                    aml.company_id AS company_id,
                    0 AS debit,
                    0 AS credit,
                    0 AS balance,
                    0 AS amount_currency,
                    aml.currency_id AS currency_id,
                    rc.id AS company_currency_id,
                    am.name AS reference,
                    'product_detail' AS type_key,
                    aml.name AS note,
                    aml.product_id AS product_id,
                    aml.product_uom_id AS product_uom_id,
                    aml.quantity AS quantity,
                    aml.price_unit AS price_unit,
                    aml.discount AS discount,
                    aml.price_subtotal AS price_subtotal,
                    aml.price_total AS price_total,
                    (aml.price_total - aml.price_subtotal) AS tax_amount,
                    1 AS line_sort,
                    'product' AS line_type
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN res_company comp ON comp.id = aml.company_id
                JOIN res_currency rc ON rc.id = comp.currency_id
                WHERE am.state = 'posted'
                AND aml.display_type = 'product'
                AND am.move_type IN ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
                AND aml.partner_id IS NOT NULL
            )
        """)

    @api.depends('type_key')
    def _compute_type_display(self):
        type_translations = {
            'out_invoice': _('Invoice'),
            'in_invoice': _('Bill'),
            'out_refund': _('Credit Note'),
            'in_refund': _('Credit Note'),
            'bank_payment': _('Bank Payment'),
            'check_payment': _('Check'),
            'manual_payment': _('Manual Payment'),
            'purchase': _('Purchase'),
            'sale': _('Sale'),
            'journal_entry': _('Journal Entry'),
            'product_detail': _('Product'),
        }
        for rec in self:
            rec.type = type_translations.get(rec.type_key, rec.type_key)

    @api.depends('partner_id', 'date', 'move_id', 'balance')
    @api.depends_context('date_from', 'action_name', 'skip_opening')
    def _compute_cumulated_balance(self):
        """Compute cumulated balance with inline initial balance.

        Uses raw SQL for initial balances because debit/credit are stored
        columns in the database view, making aggregation efficient.
        """
        initial_balances = self._fetch_initial_balances_sql()
        self._cumulate_by_group('balance', 'cumulated_balance', initial_balances)


    def _collect_rate_keys(self, summary_recs, try_currency, has_tcmb_rate, has_try_rate=False):
        """Collect unique (company, date) and (company, date, currency) keys for batch SQL.

        USD lines need try_rate only when no per-record TCMB rate is set (fallback path).
        3rd-currency lines (e.g. EUR) always need try_rate + inv_rate for the cross-rate
        calculation regardless of TCMB presence, because TCMB rate is USD/TRY and cannot
        be used directly for EUR/TRY conversion.
        Records with l10n_tr_tcmb_try_rate set skip all cache lookups (direct TRY rate).
        """
        try_rate_keys = set()
        inv_rate_keys = set()
        for rec in summary_recs:
            if not (rec.currency_id and rec.currency_id != try_currency):
                continue
            if not (rec.date and rec.company_id):
                continue
            # Highest priority: direct TRY rate — no cache lookup needed
            try_rate_field = 0.0
            if has_try_rate and rec.move_id:
                try_rate_field = rec.move_id.l10n_tr_tcmb_try_rate or 0.0
            if try_rate_field:
                continue
            is_third = rec.currency_id != rec.company_currency_id
            tcmb_rate = 0.0
            if has_tcmb_rate and rec.move_id:
                tcmb_rate = rec.move_id.l10n_tr_tcmb_rate or 0.0
            # USD lines: add to cache only when no TCMB rate (they use tcmb_rate otherwise).
            # 3rd-currency lines: always add — cross-rate fallback is required even with TCMB.
            if not tcmb_rate or is_third:
                try_rate_keys.add((rec.company_id.id, str(rec.date)))
            if is_third:
                inv_rate_keys.add((rec.company_id.id, str(rec.date), rec.currency_id.id))
        return try_rate_keys, inv_rate_keys

    def _fetch_try_rate_cache(self, try_rate_keys, try_currency):
        """Batch-fetch TRY rates for the given (company_id, date) key set.

        Returns a dict: {(company_id, date_str): rate}
        Rates are stored as units-of-currency per 1 USD in res_currency_rate.
        """
        try_rate_cache = {}
        if not (try_rate_keys and try_currency):
            return try_rate_cache
        values_list = ", ".join(
            self.env.cr.mogrify("(%s, %s::date)", (cid, dt)).decode()
            for cid, dt in try_rate_keys
        )
        self.env.cr.execute(f"""
            SELECT v.company_id, v.dt, r.rate
            FROM (VALUES {values_list}) AS v(company_id, dt)
            LEFT JOIN LATERAL (
                SELECT rate
                FROM res_currency_rate
                WHERE currency_id = %s
                  AND company_id = v.company_id
                  AND name <= v.dt
                ORDER BY name DESC
                LIMIT 1
            ) r ON TRUE
        """, (try_currency.id,))
        for company_id, dt, rate in self.env.cr.fetchall():
            try_rate_cache[(company_id, str(dt))] = rate or 0.0
        return try_rate_cache

    def _fetch_inv_rate_cache(self, inv_rate_keys):
        """Batch-fetch rates for 3rd currencies (e.g. EUR) for cross-rate calculation.

        Returns a dict: {(company_id, date_str, currency_id): rate}
        Cross rate formula: EUR/TRY = try_rate / eur_rate (both units per 1 USD).
        """
        inv_rate_cache = {}
        if not inv_rate_keys:
            return inv_rate_cache
        values_list = ", ".join(
            self.env.cr.mogrify("(%s, %s::date, %s)", (cid, dt, cur_id)).decode()
            for cid, dt, cur_id in inv_rate_keys
        )
        self.env.cr.execute(f"""
            SELECT v.company_id, v.dt, v.currency_id, r.rate
            FROM (VALUES {values_list}) AS v(company_id, dt, currency_id)
            LEFT JOIN LATERAL (
                SELECT rate
                FROM res_currency_rate
                WHERE currency_id = v.currency_id
                  AND company_id = v.company_id
                  AND name <= v.dt
                ORDER BY name DESC
                LIMIT 1
            ) r ON TRUE
        """)
        for company_id, dt, currency_id, rate in self.env.cr.fetchall():
            inv_rate_cache[(company_id, str(dt), currency_id)] = rate or 0.0
        return inv_rate_cache

    def _apply_tr_value(self, rec, try_currency, has_tcmb_rate, try_rate_cache, inv_rate_cache, has_try_rate=False):
        """Assign amount_tr_currency and tr_rate_display for a single record.

        Branch logic:
        - TRY line: amount_currency is already TRY, rate = "1.0000"
        - Non-TRY, direct TRY rate set (l10n_tr_tcmb_try_rate): amount_currency × try_rate
        - Non-TRY, TCMB rate set, USD line: balance × tcmb_rate (tcmb_rate is USD/TRY)
        - Non-TRY, TCMB rate set, 3rd-currency (EUR): amount_currency × tcmb_rate × try_rate
          (tcmb_rate is EUR/USD official; try_rate is TRY/USD from daily rates → EUR/TRY)
        - Non-TRY, no TCMB rate: pure daily cross-rate from res_currency_rate
        - No currency: 0.0, "N/A"
        """
        if rec.currency_id == try_currency:
            rec.amount_tr_currency = rec.amount_currency
            rec.tr_rate_display = "1.0000"
            return

        if rec.currency_id:
            # Highest priority: user-supplied direct TRY rate
            try_rate_field = 0.0
            if has_try_rate and rec.move_id:
                try_rate_field = rec.move_id.l10n_tr_tcmb_try_rate or 0.0
            if try_rate_field:
                rec.tr_rate_display = f"{try_rate_field:.4f}"
                rec.amount_tr_currency = float_round(
                    rec.amount_currency * try_rate_field,
                    precision_digits=2
                )
                return

            is_third_currency = rec.currency_id != rec.company_currency_id
            tcmb_rate = 0.0
            if has_tcmb_rate and rec.move_id:
                tcmb_rate = rec.move_id.l10n_tr_tcmb_rate or 0.0

            if tcmb_rate:
                if is_third_currency:
                    # tcmb_rate is EUR/USD (official TCMB rate on the invoice).
                    # try_rate is TRY/USD from res_currency_rate.
                    # EUR/TRY = tcmb_rate × try_rate
                    try_rate = try_rate_cache.get((rec.company_id.id, str(rec.date)), 0.0)
                    if try_rate:
                        eur_try_rate = tcmb_rate * try_rate
                        rec.tr_rate_display = f"{eur_try_rate:.4f}"
                        rec.amount_tr_currency = float_round(
                            rec.amount_currency * eur_try_rate,
                            precision_digits=2
                        )
                    else:
                        rec.amount_tr_currency = rec.balance or 0.0
                        rec.tr_rate_display = "0.0000"
                else:
                    # tcmb_rate is USD/TRY for company-currency (USD) lines.
                    rec.tr_rate_display = f"{tcmb_rate:.4f}"
                    rec.amount_tr_currency = float_round(
                        rec.balance * tcmb_rate,
                        precision_digits=2
                    )
            else:
                # Fallback: batch-fetched daily rates from res_currency_rate.
                # For 3rd currencies compute cross rate: EUR/TRY = try_rate / eur_rate
                # (both stored as units-of-currency per 1 USD in res_currency_rate).
                try_rate = try_rate_cache.get((rec.company_id.id, str(rec.date)), 0.0)
                if is_third_currency:
                    inv_rate = inv_rate_cache.get(
                        (rec.company_id.id, str(rec.date), rec.currency_id.id), 0.0
                    )
                    if try_rate and inv_rate:
                        cross_rate = try_rate / inv_rate
                        rec.tr_rate_display = f"{cross_rate:.4f}"
                        rec.amount_tr_currency = float_round(
                            rec.amount_currency * cross_rate,
                            precision_digits=2
                        )
                    else:
                        rec.amount_tr_currency = rec.balance or 0.0
                        rec.tr_rate_display = "0.0000"
                else:
                    if try_rate:
                        rec.tr_rate_display = f"{try_rate:.4f}"
                        rec.amount_tr_currency = float_round(
                            rec.balance * try_rate,
                            precision_digits=2
                        )
                    else:
                        rec.amount_tr_currency = rec.balance or 0.0
                        rec.tr_rate_display = "0.0000"
        else:
            rec.amount_tr_currency = 0.0
            rec.tr_rate_display = "N/A"

    @api.depends('currency_id', 'amount_currency', 'balance', 'date', 'company_id', 'move_id')
    def _compute_amount_tr_currency(self):
        """Compute TRY equivalent value for the transaction.

        - TRY document: amount_tr_currency = amount_currency (already TRY)
        - Non-TRY, company-currency line with TCMB rate: balance × tcmb_rate (USD/TRY)
        - Non-TRY, 3rd-currency line (e.g. EUR): cross-rate fallback (TCMB is not EUR/TRY)
        - Non-TRY other: balance × res.currency.rate for TRY (batch-fetched)
        """
        try_currency = self._get_try_currency()
        has_tcmb_rate = 'l10n_tr_tcmb_rate' in self.env['account.move']._fields
        has_try_rate = 'l10n_tr_tcmb_try_rate' in self.env['account.move']._fields
        summary_recs = self._zero_product_fields('amount_tr_currency', 'tr_rate_display')

        try_rate_keys, inv_rate_keys = self._collect_rate_keys(
            summary_recs, try_currency, has_tcmb_rate, has_try_rate=has_try_rate
        )
        try_rate_cache = self._fetch_try_rate_cache(try_rate_keys, try_currency)
        inv_rate_cache = self._fetch_inv_rate_cache(inv_rate_keys)

        for rec in summary_recs:
            self._apply_tr_value(rec, try_currency, has_tcmb_rate, try_rate_cache, inv_rate_cache, has_try_rate=has_try_rate)

    @api.depends('partner_id', 'currency_id', 'date', 'move_id', 'amount_tr_currency')
    @api.depends_context('date_from', 'skip_opening')
    def _compute_cumulated_amount_tr_currency(self):
        """Compute cumulative TRY value with initial balance support.

        Uses ORM search (not raw SQL) because amount_tr_currency is a
        computed field that is not stored in the database view.
        """
        initial_balances = self._fetch_initial_tr_balances()
        self._cumulate_by_group('amount_tr_currency', 'cumulated_amount_tr_currency', initial_balances)

    @api.depends('amount_tr_currency')
    def _compute_amount_tr_debit_credit(self):
        """Split TRY amount into debit (positive) and credit (negative)."""
        summary_recs = self._zero_product_fields('amount_tr_debit', 'amount_tr_credit')
        for rec in summary_recs:
            rec.amount_tr_debit = rec.amount_tr_currency if rec.amount_tr_currency > 0 else 0.0
            rec.amount_tr_credit = abs(rec.amount_tr_currency) if rec.amount_tr_currency < 0 else 0.0

    @api.model
    def get_opening_balance_value(self, partner_id, date_from, is_tr_report=False,
                                  filter_field=None, filter_value=None):
        """Return opening balances for toolbar display and export.

        When called without filter_field, returns per-currency dict for toolbar.
        When called with filter_field/filter_value, returns a single dict with
        debit/credit/balance/currency/date for the filtered group.

        Args:
            partner_id: Partner ID to compute balances for.
            date_from: Date string (YYYY-MM-DD). Records before this date.
            is_tr_report: If True, compute TRY-equivalent balances.
            filter_field: Optional ORM domain field to filter by (e.g. 'currency_id.name').
            filter_value: Value to match for filter_field.

        Returns:
            dict: Per-currency mapping when no filter, or single balance dict when filtered.
        """
        if not partner_id or not date_from:
            if filter_field is not None:
                currency = filter_value if filter_field == 'currency_id.name' else ReportConstants.CURRENCY_TRY
                return {'debit': 0.0, 'credit': 0.0, 'balance': 0.0, 'currency': currency, 'date': ''}
            return {}

        # --- Filtered mode: return single balance dict for a specific group ---
        if filter_field is not None:
            import datetime as _dt
            from datetime import timedelta
            date_obj = _dt.datetime.strptime(date_from, '%Y-%m-%d')
            opening_date = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')

            domain = [
                ('partner_id', '=', partner_id),
                ('move_id.journal_id.code', 'not in', ReportConstants.EXCLUDED_JOURNAL_CODES),
                ('date', '<', date_from),
                ('company_id', 'in', self.env.companies.ids),
            ]
            if filter_field and filter_value:
                domain.append((filter_field, '=', filter_value))

            records = self.search(domain)

            if is_tr_report:
                total = sum(r.amount_tr_currency for r in records)
                debit = sum(r.amount_tr_currency for r in records if r.amount_tr_currency > 0)
                credit = sum(abs(r.amount_tr_currency) for r in records if r.amount_tr_currency < 0)
                return {
                    'debit': debit, 'credit': credit, 'balance': total,
                    'currency': ReportConstants.CURRENCY_TRY, 'date': opening_date,
                }

            currency = ReportConstants.CURRENCY_TRY
            if filter_field == 'currency_id.name':
                currency = filter_value
            elif records:
                currency = records[0].currency_id.name or ReportConstants.CURRENCY_TRY

            debit = sum(records.mapped('debit'))
            credit = sum(records.mapped('credit'))
            return {
                'debit': debit, 'credit': credit, 'balance': debit - credit,
                'currency': currency, 'date': opening_date,
            }

        # --- Unfiltered mode: return per-currency dict for toolbar ---
        if is_tr_report:
            prior_records = self.search([
                ('date', '<', date_from),
                ('partner_id', '=', partner_id),
                ('line_type', '=', 'summary'),
                ('company_id', 'in', self.env.companies.ids),
                ('move_id.journal_id.code', 'not in', ReportConstants.EXCLUDED_JOURNAL_CODES),
            ])
            total = sum(r.amount_tr_currency for r in prior_records)
            debit = sum(r.amount_tr_currency for r in prior_records if r.amount_tr_currency > 0)
            credit = sum(abs(r.amount_tr_currency) for r in prior_records if r.amount_tr_currency < 0)
            try_currency = self._get_try_currency()
            symbol = try_currency.symbol if try_currency else '₺'
            return {ReportConstants.CURRENCY_TRY: {
                'opening': total, 'symbol': symbol, 'debit': debit, 'credit': credit}}

        self.env.cr.execute("""
            SELECT rc.name, rc.symbol,
                   SUM(amlr.debit), SUM(amlr.credit),
                   SUM(amlr.debit) - SUM(amlr.credit)
            FROM account_move_line_report amlr
            JOIN account_move am ON am.id = amlr.move_id
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN res_company comp ON comp.id = amlr.company_id
            JOIN res_currency rc ON rc.id = comp.currency_id
            WHERE amlr.date < %s
            AND amlr.partner_id = %s
            AND amlr.line_type = 'summary'
            AND amlr.company_id = ANY(%s)
            AND aj.code NOT IN %s
            GROUP BY rc.name, rc.symbol
        """, (date_from, partner_id, list(self.env.companies.ids), ReportConstants.EXCLUDED_JOURNAL_CODES))

        result = {}
        for currency_name, symbol, debit, credit, balance in self.env.cr.fetchall():
            result[currency_name] = {
                'opening': balance, 'symbol': symbol,
                'debit': debit, 'credit': credit,
            }
        return result
