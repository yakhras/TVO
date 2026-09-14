# -*- coding: utf-8 -*-
"""Excel/PDF export controller for partner balance reports."""

import datetime
import json
import operator
import logging

from odoo import http
from odoo.http import content_disposition, request
from odoo.tools import osutil
from odoo.tools.translate import _
from odoo.addons.web.controllers.export import (
    ExportFormat as BaseExportFormat,
    GroupsTreeNode as BaseGroupsTreeNode,
)

from ..services.balance_export import (
    BalanceDataService,
    BalanceXlsxWriter,
    GroupedBalanceXlsxWriter,
    AgedBalanceXlsxWriter,
    LedgerBalanceXlsxWriter,
    AgedSummaryXlsxWriter,
    FieldMapping,
    DirectionResolver,
    render_balance_pdf,
    format_pdf_value,
    format_pdf_row,
)

_logger = logging.getLogger(__name__)


class BalanceExcelExport(BaseExportFormat, http.Controller):
    """Controller for exporting partner balance data to Excel and PDF."""

    BUCKET_ORDER = ['current', '1_30', '31_60', '61_90', '91_120', 'older']

    # Internal codes an external caller (JS/XML) can pass as `action_name` to select a
    # specific PDF title; kept untranslated since they're also used as `==` comparison
    # keys (e.g. `ctx.get('action_name') == 'Statement in TRY'`). Never shown directly.
    ACTION_TITLES = {
        'Statement in TRY': lambda env: env._('Statement in TRY'),
        'Ledger Balance in TRY': lambda env: env._('Ledger Balance in TRY'),
        'Aged Balance in TRY': lambda env: env._('Aged Balance in TRY'),
    }

    def _lang_env(self, lang):
        """An env scoped to `lang`, for translations that must follow the report's
        resolved language rather than the backend user's own session language.
        The bare `_()` helper resolves its language by inspecting the caller's
        frame (falling back to `request.env.lang`, the wrong one here), so any
        text that ends up in the PDF must be translated via `env._(...)` on an
        env explicitly scoped like this instead."""
        return request.env(context=dict(request.env.context, lang=lang)) if lang else request.env

    def _bucket_labels(self, lang):
        """Built per-call (not a class attribute) so translation resolves the
        report's language, not the one active at module load time."""
        env = self._lang_env(lang)
        return {
            'current': env._('Current'),
            '1_30': env._('1-30 Days'),
            '31_60': env._('31-60 Days'),
            '61_90': env._('61-90 Days'),
            '91_120': env._('91-120 Days'),
            'older': env._('> 120 Days'),
        }

    def _resolve_title(self, action_name, lang):
        """Translate a PDF title, resolving known internal action_name codes to
        their translated display string; falls back to the raw value or the
        default title."""
        env = self._lang_env(lang)
        if action_name in self.ACTION_TITLES:
            return self.ACTION_TITLES[action_name](env)
        return action_name or env._('Statement of Account')

    def _build_export_filename(self, ctx):
        """Build a descriptive filename: '{partner} - {ReportType} - {Currency} - {date}'"""
        partner_name = ctx.get('partner_name', '') or 'Export'
        report_type = 'Aged' if ctx.get('report_type') == 'aged' else 'Ledger'
        currency = 'TRY' if ctx.get('action_name') == 'Statement in TRY' else 'USD'
        today = datetime.date.today().strftime('%Y-%m-%d')
        return osutil.clean_filename(f"{partner_name} - {report_type} - {currency} - {today}")

    def _build_summary_filename(self, label):
        """Build a summary-report filename: '{label} - {date}'"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        return osutil.clean_filename(f"{label} - {today}")

    def _parse_list_export_params(self, data):
        """Parse the {model, fields, ids, domain, import_compat, context} JSON payload
        shared by the flat/aged xlsx and pdf routes, and resolve the target Model."""
        params = json.loads(data)
        model, fields, ids, domain, import_compat = operator.itemgetter(
            'model', 'fields', 'ids', 'domain', 'import_compat'
        )(params)

        Model = request.env[model].with_context(
            import_compat=import_compat,
            **params.get('context', {})
        )
        if not Model._is_an_ordinary_table():
            fields = [f for f in fields if f['name'] != 'id']

        field_names = [f['name'] for f in fields]
        return params, Model, fields, field_names, ids, domain

    @property
    def content_type(self):
        return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    @property
    def extension(self):
        return '.xlsx'

    # ------------------------------------------------------------------
    # Partner statement (flat / grouped)
    # ------------------------------------------------------------------

    @http.route('/web/balance_export/xlsx', type='http', auth="user")
    def index(self, data):
        return self.base(data)

    def base(self, data):
        """Main xlsx export handler."""
        params, Model, fields, field_names, ids, domain = self._parse_list_export_params(data)
        import_compat = params['import_compat']
        columns_headers = (
            field_names if import_compat
            else [f['label'].strip() for f in fields]
        )

        groupby = params.get('groupby')
        if not import_compat and groupby:
            response_data = self._export_grouped(Model, fields, field_names, ids, domain, groupby, params)
        else:
            response_data = self._export_flat(Model, field_names, columns_headers, ids, domain, params)

        return request.make_response(
            response_data,
            headers=[
                ('Content-Disposition', content_disposition(
                    self._build_export_filename(params.get('context', {})) + self.extension
                )),
                ('Content-Type', self.content_type),
            ],
        )

    @http.route('/web/balance_export/pdf', type='http', auth="user")
    def index_pdf(self, data):
        params, Model, fields, field_names, ids, domain = self._parse_list_export_params(data)
        columns_headers = [f['label'].strip() for f in fields]

        gathered = self._gather_flat_export_data(Model, field_names, ids, domain, params)
        ctx = gathered['ctx']
        lang, direction = DirectionResolver.for_partner_report(request.env, ctx.get('default_partner_id'))

        values = self._build_statement_pdf_values(columns_headers, gathered, ctx, lang, direction)
        pdf_bytes = render_balance_pdf(
            request.env,
            'partner_balance.action_report_balance_statement',
            'partner_balance.report_balance_statement_document',
            values,
        )
        filename = self._build_export_filename(ctx)
        return request.make_response(pdf_bytes, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename + '.pdf')),
        ])

    def _fetch_product_lines(self, records, show_products):
        """Fetch product detail lines grouped by move_id.

        Args:
            records: recordset of account.move.line.report to inspect
            show_products: boolean flag from context

        Returns:
            dict mapping move_id -> list of account.move.line records
        """
        if not show_products:
            return {}

        invoice_types = ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
        move_ids = records.filtered(
            lambda r: r.type_key in invoice_types
        ).mapped('move_id').ids

        if not move_ids:
            return {}

        product_lines_by_move = {}
        aml = request.env['account.move.line'].sudo().search([
            ('move_id', 'in', move_ids),
            ('display_type', '=', 'product'),
        ])
        for line in aml:
            product_lines_by_move.setdefault(line.move_id.id, []).append(line)
        return product_lines_by_move

    def _gather_flat_export_data(self, Model, field_names, ids, domain, params):
        """Fetch & compute all data needed for a flat (non-grouped) balance export,
        shared by the xlsx writer and the PDF renderer."""
        records = Model.browse(ids) if ids else Model.search(domain, offset=0, limit=False, order=False)
        export_data = records.export_data(field_names).get('datas', [])

        ctx = params.get('context', {})
        skip_opening = ctx.get('skip_opening', False)
        data_service = BalanceDataService.from_params(request.env, params)

        product_lines_by_move = self._fetch_product_lines(
            records, ctx.get('show_products', False)
        )

        if skip_opening:
            opening_data = {'balance': 0.0, 'debit': 0.0, 'credit': 0.0}
        else:
            opening_data = data_service.get_opening_balance()

        return {
            'records': records,
            'export_data': export_data,
            'ctx': ctx,
            'skip_opening': skip_opening,
            'data_service': data_service,
            'product_lines_by_move': product_lines_by_move,
            'opening_data': opening_data,
        }

    def _export_flat(self, Model, field_names, columns_headers, ids, domain, params):
        """Export non-grouped data to xlsx."""
        gathered = self._gather_flat_export_data(Model, field_names, ids, domain, params)
        ctx = gathered['ctx']
        skip_opening = gathered['skip_opening']
        export_data = gathered['export_data']
        records = gathered['records']
        product_lines_by_move = gathered['product_lines_by_move']
        opening_data = gathered['opening_data']

        lang, direction = DirectionResolver.for_partner_report(request.env, ctx.get('default_partner_id'))

        with BalanceXlsxWriter(columns_headers, len(export_data), direction=direction) as writer:
            header_end_row = writer.write_metadata(ctx, gathered['data_service'])
            data_start_row = writer.write_header(row=header_end_row)

            if not skip_opening and opening_data['balance'] != 0.0:
                period_start_row, opening_debit, opening_credit = writer.write_opening_balance_row(
                    data_start_row, opening_data
                )
            else:
                period_start_row = data_start_row
                opening_debit = opening_credit = 0
                opening_data['balance'] = 0.0

            writer.write_data_rows(period_start_row, export_data, opening_data['balance'],
                        product_lines=product_lines_by_move, records=records)

            product_row_count = sum(len(v) + 1 for v in product_lines_by_move.values())  # +1 for header per group
            totals_row = period_start_row + len(export_data) + product_row_count + 1
            writer.write_totals(totals_row, export_data, opening_debit, opening_credit)

        return writer.value

    def _sanitize_row(self, row):
        """Convert a raw export row into HTML-safe values (mirrors BalanceXlsxWriter._safe_value)."""
        return [BalanceXlsxWriter._safe_value(v) for v in row]

    def _period_label(self, data_service, lang):
        oldest_date = data_service.get_oldest_date(self._lang_env(lang))
        start = data_service.date_from or oldest_date
        end = data_service.date_to or datetime.date.today().strftime('%Y-%m-%d')
        return f"{start} - {end}"

    def _base_pdf_values(self, title, lang, direction='ltr', partner_name='', period_label='', as_of_label=''):
        return {
            'lang': lang,
            'direction': direction,
            'title': title,
            'partner_name': partner_name,
            'period_label': period_label,
            'as_of_label': as_of_label,
            'generated_label': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    def _build_product_rows(self, product_lines_by_move, lang):
        """Flatten account.move.line product records into plain formatted dicts
        for the PDF template (mirrors BalanceXlsxWriter._write_product_block).

        Product/UoM names are read through a `lang`-scoped recordset so a
        product's own translated name (if one exists) is used, matching the
        report's resolved language rather than the backend user's session one.
        """
        digits = FieldMapping.get_max_decimal_places(request.env)
        flattened = {}
        for move_id, lines in product_lines_by_move.items():
            flattened[move_id] = [{
                # `display_default_code=False` drops the "[INTERNAL-REF]" prefix
                # `display_name` would otherwise include — PDF-only, per request;
                # Excel/on-screen keep the reference via the default display_name.
                'product': line.product_id.with_context(
                    lang=lang, display_default_code=False
                ).display_name or '',
                'qty': format_pdf_value(request.env, line.quantity, lang, digits=digits),
                'uom': (line.product_uom_id.with_context(lang=lang) if lang else line.product_uom_id).name or '',
                'unit_price': format_pdf_value(request.env, line.price_unit, lang, digits=digits),
                'discount': format_pdf_value(request.env, line.discount or 0, lang, digits=digits),
                'tax': format_pdf_value(
                    request.env, line.price_total - line.price_subtotal, lang, digits=digits
                ),
                'total': format_pdf_value(request.env, line.price_total, lang, digits=digits),
            } for line in lines]
        return flattened

    def _translate_headers(self, headers, lang):
        """Translate client-supplied column header labels into the report's
        resolved language. These arrive as plain strings captured from the
        currently rendered list view (in the viewing user's own session
        language), so — unlike the static QWeb text elsewhere in the template —
        they don't automatically follow the report's target `lang`.

        These labels exist today only as field-description/view-arch
        translations — a separate storage from the "code translations" that a
        `_()` lookup searches — so translating the raw text needs it registered
        as a code translation too. That in turn needs a literal `_('...')` call
        (the `--i18n-export` string extractor only recognizes bare calls to the
        name `_`, not an attribute call like `env._(...)`, and not a variable),
        and to pick up `lang` instead of the ambient request/session language,
        the bare `_()` helper needs a local variable literally named `context`
        holding it (see `odoo.tools.translate._get_lang`) — hence both odd
        details below.
        """
        context = {'lang': lang}  # noqa: F841 -- read by `_()`'s frame introspection
        known = {
            'Date': _('Date'),
            'Type': _('Type'),
            'Reference': _('Reference'),
            'Note': _('Note'),
            'Debit': _('Debit'),
            'Credit': _('Credit'),
            'Balance': _('Balance'),
            # The export payload carries the `cumulated_balance` field's own
            # description, not the list view's `string="Balance"` arch override
            # it's actually shown under on screen — map it to the same "Balance"
            # translation so the PDF header matches what the view displays.
            'Cumulated Balance': _('Balance'),
            'Origin Amount': _('Origin Amount'),
            'Currency': _('Currency'),
            'Rate': _('Rate'),
            'Document': _('Document'),
            'Due Date': _('Due Date'),
            'Days': _('Days'),
            'Residual': _('Residual'),
            'TRY Residual': _('TRY Residual'),
            'Bucket': _('Bucket'),
        }
        return [known.get(h, h) for h in headers]

    def _build_statement_pdf_values(self, columns_headers, gathered, ctx, lang, direction='ltr'):
        columns_headers = self._translate_headers(columns_headers, lang)
        export_data = gathered['export_data']
        opening_data = gathered['opening_data']
        skip_opening = gathered['skip_opening']
        data_service = gathered['data_service']
        records = gathered['records']

        digits = FieldMapping.get_max_decimal_places(request.env)
        numeric_indices = [
            FieldMapping.COLUMNS['debit'], FieldMapping.COLUMNS['credit'],
            FieldMapping.COLUMNS['balance'], FieldMapping.COLUMNS['amount_currency'],
        ]

        rows = [
            format_pdf_row(request.env, self._sanitize_row(r), numeric_indices, lang, digits=digits)
            for r in export_data
        ]
        row_move_ids = [r.move_id.id for r in records]

        opening_row = None
        opening_debit = opening_credit = 0.0
        if not skip_opening and opening_data['balance'] != 0.0:
            opening_row = format_pdf_row(
                request.env,
                self._sanitize_row(FieldMapping.create_opening_balance_row(opening_data, env=self._lang_env(lang))),
                numeric_indices, lang, digits=digits,
            )
            opening_debit = opening_data.get('debit', 0.0)
            opening_credit = opening_data.get('credit', 0.0)

        total_debit = opening_debit
        total_credit = opening_credit
        for row in export_data:
            total_debit += FieldMapping.get_numeric_value(row, 'debit')
            total_credit += FieldMapping.get_numeric_value(row, 'credit')

        totals_row = [''] * len(columns_headers)
        totals_row[0] = self._lang_env(lang)._('Total')
        debit_idx = FieldMapping.COLUMNS['debit']
        credit_idx = FieldMapping.COLUMNS['credit']
        balance_idx = FieldMapping.COLUMNS['balance']
        if debit_idx < len(totals_row):
            totals_row[debit_idx] = format_pdf_value(request.env, round(total_debit, 2), lang, digits=digits)
        if credit_idx < len(totals_row):
            totals_row[credit_idx] = format_pdf_value(request.env, round(total_credit, 2), lang, digits=digits)
        if balance_idx < len(totals_row):
            totals_row[balance_idx] = format_pdf_value(
                request.env, round(total_debit - total_credit, 2), lang, digits=digits
            )

        show_products = ctx.get('show_products', False)
        product_lines_by_move = (
            self._build_product_rows(gathered['product_lines_by_move'], lang) if show_products else {}
        )

        action_name = ctx.get('action_name', '')
        values = self._base_pdf_values(
            title=self._resolve_title(action_name, lang),
            lang=lang,
            direction=direction,
            partner_name=ctx.get('partner_name', ''),
            period_label=self._period_label(data_service, lang),
        )
        values.update({
            'columns_headers': columns_headers,
            'opening_row': opening_row,
            'rows': list(zip(rows, row_move_ids)),
            'totals_row': totals_row,
            'date_col_indices': {FieldMapping.COLUMNS['date']},
            'show_products': show_products,
            'product_lines_by_move': product_lines_by_move,
        })
        return values

    # ------------------------------------------------------------------
    # Aged balance (per-partner)
    # ------------------------------------------------------------------

    @http.route('/web/aged_balance_export/xlsx', type='http', auth="user")
    def aged_index(self, data):
        return self.aged_base(data)

    def aged_base(self, data):
        """xlsx export handler for aged balance."""
        params, Model, fields, field_names, ids, domain = self._parse_list_export_params(data)
        response_data = self._export_aged_grouped(Model, fields, field_names, ids, domain, params)

        return request.make_response(
            response_data,
            headers=[
                ('Content-Disposition', content_disposition(
                    self._build_export_filename(params.get('context', {})) + self.extension
                )),
                ('Content-Type', self.content_type),
            ],
        )

    @http.route('/web/aged_balance_export/pdf', type='http', auth="user")
    def aged_index_pdf(self, data):
        params, Model, fields, field_names, ids, domain = self._parse_list_export_params(data)
        columns_headers = [f['label'].strip() for f in fields]

        gathered = self._gather_aged_export_data(Model, field_names, ids, domain, params)
        ctx = gathered['ctx']
        lang, direction = DirectionResolver.for_partner_report(request.env, ctx.get('default_partner_id'))

        values = self._build_aged_pdf_values(fields, columns_headers, gathered, ctx, lang, direction)
        pdf_bytes = render_balance_pdf(
            request.env,
            'partner_balance.action_report_aged_balance',
            'partner_balance.report_aged_balance_document',
            values,
        )
        filename = self._build_export_filename(ctx)
        return request.make_response(pdf_bytes, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename + '.pdf')),
        ])

    def _gather_aged_export_data(self, Model, field_names, ids, domain, params):
        """Fetch & bucket-group all data needed for an aged balance export,
        shared by the xlsx writer and the PDF renderer — manual grouping, no read_group."""
        domain = [('id', 'in', ids)] if ids else domain
        all_records = Model.search(domain, offset=0, limit=False,
                                   order='bucket asc, date_maturity asc, date asc, id asc')
        export_data = all_records.export_data(field_names).get('datas', [])

        groups = {k: [] for k in self.BUCKET_ORDER}
        record_groups = {k: [] for k in self.BUCKET_ORDER}
        for record, row in zip(all_records, export_data):
            bucket = record.bucket or 'current'
            if bucket in groups:
                groups[bucket].append(row)
                record_groups[bucket].append(record)

        ctx = params.get('context', {})
        is_tr = ctx.get('action_name') == 'Statement in TRY'
        data_service = BalanceDataService.from_params(request.env, params)

        show_products = ctx.get('show_products', False)
        product_lines_by_move = self._fetch_product_lines(all_records, show_products)

        return {
            'all_records': all_records,
            'export_data': export_data,
            'groups': groups,
            'record_groups': record_groups,
            'ctx': ctx,
            'is_tr': is_tr,
            'data_service': data_service,
            'product_lines_by_move': product_lines_by_move,
        }

    def _export_aged_grouped(self, Model, fields, field_names, ids, domain, params):
        """Export aged balance grouped by bucket to xlsx."""
        gathered = self._gather_aged_export_data(Model, field_names, ids, domain, params)
        ctx = gathered['ctx']
        lang, direction = DirectionResolver.for_partner_report(request.env, ctx.get('default_partner_id'))

        with AgedBalanceXlsxWriter(fields, len(gathered['export_data']), is_tr_report=gathered['is_tr'],
                                    direction=direction) as writer:
            row = writer.write_metadata(ctx, gathered['data_service'])
            for bucket_key in self.BUCKET_ORDER:
                rows = gathered['groups'][bucket_key]
                if not rows:
                    continue
                label = self._bucket_labels(lang)[bucket_key]
                row = writer.write_aged_group(
                    row, label, rows,
                    records=gathered['record_groups'][bucket_key],
                    product_lines=gathered['product_lines_by_move'],
                )

        return writer.value

    def _build_aged_pdf_values(self, fields, columns_headers, gathered, ctx, lang, direction='ltr'):
        columns_headers = self._translate_headers(columns_headers, lang)
        residual_field = 'amount_residual_try' if gathered['is_tr'] else 'amount_residual'
        residual_idx = next(
            (i for i, f in enumerate(fields) if f['name'] == residual_field), None
        )
        digits = FieldMapping.get_max_decimal_places(request.env)
        numeric_indices = [i for i, f in enumerate(fields) if f.get('type') in ('monetary', 'float')]
        date_col_indices = {i for i, f in enumerate(fields) if f.get('type') == 'date'}

        show_products = ctx.get('show_products', False)
        product_lines_by_move = (
            self._build_product_rows(gathered['product_lines_by_move'], lang) if show_products else {}
        )

        buckets = []
        for bucket_key in self.BUCKET_ORDER:
            rows = gathered['groups'][bucket_key]
            if not rows:
                continue
            total = 0.0
            sanitized_rows = []
            for row in rows:
                sanitized_rows.append(
                    format_pdf_row(request.env, self._sanitize_row(row), numeric_indices, lang, digits=digits)
                )
                if residual_idx is not None and residual_idx < len(row):
                    val = row[residual_idx]
                    if isinstance(val, (int, float)):
                        total += val
            row_move_ids = [r.move_id.id for r in gathered['record_groups'][bucket_key]]

            total_row = [''] * len(columns_headers)
            total_row[0] = self._lang_env(lang)._('Total')
            if residual_idx is not None and residual_idx < len(total_row):
                total_row[residual_idx] = format_pdf_value(request.env, round(total, 2), lang, digits=digits)

            buckets.append({
                'label': '%s (%s)' % (self._bucket_labels(lang)[bucket_key], len(rows)),
                'rows': list(zip(sanitized_rows, row_move_ids)),
                'total_row': total_row,
            })

        env = self._lang_env(lang)
        title = env._('Aged Balance in TRY') if gathered['is_tr'] else env._('Aged Balance')
        values = self._base_pdf_values(
            title=title,
            lang=lang,
            direction=direction,
            partner_name=ctx.get('partner_name', ''),
            as_of_label=datetime.date.today().strftime('%Y-%m-%d'),
        )
        values.update({
            'columns_headers': columns_headers,
            'buckets': buckets,
            'show_products': show_products,
            'product_lines_by_move': product_lines_by_move,
            'date_col_indices': date_col_indices,
        })
        return values

    # ------------------------------------------------------------------
    # Grouped (TRY / multi-currency) statement
    # ------------------------------------------------------------------

    def _gather_grouped_export_data(self, Model, fields, field_names, ids, domain, groupby, params):
        """Fetch & tree-group data for the grouped (e.g. TRY, grouped by currency) export."""
        groupby_type = [Model._fields[x.split(':')[0]].type for x in groupby]
        domain = [('id', 'in', ids)] if ids else domain

        groups_data = Model.read_group(
            domain,
            [x if x != '.id' else 'id' for x in field_names],
            groupby,
            lazy=False
        )

        tree = BaseGroupsTreeNode(Model, field_names, groupby, groupby_type)
        for leaf in groups_data:
            tree.insert_leaf(leaf)

        ctx = params.get('context', {})
        skip_opening = ctx.get('skip_opening', False)
        data_service = BalanceDataService.from_params(request.env, params)

        all_records = Model.search(domain, offset=0, limit=False, order=False)
        product_lines_by_move = self._fetch_product_lines(
            all_records, ctx.get('show_products', False)
        )

        groupby_field = groupby[0].split(':')[0] if groupby else ''

        if skip_opening:
            opening_balances = {}
        else:
            opening_balances = data_service.get_opening_balances_by_group(tree, groupby_field)
            data_service.update_group_running_balances(tree, opening_balances)

        return {
            'tree': tree,
            'ctx': ctx,
            'data_service': data_service,
            'opening_balances': opening_balances,
            'product_lines_by_move': product_lines_by_move,
        }

    def _export_grouped(self, Model, fields, field_names, ids, domain, groupby, params):
        """Export grouped data to xlsx."""
        gathered = self._gather_grouped_export_data(Model, fields, field_names, ids, domain, groupby, params)
        tree = gathered['tree']
        ctx = gathered['ctx']
        data_service = gathered['data_service']

        lang, direction = DirectionResolver.for_partner_report(request.env, ctx.get('default_partner_id'))

        with GroupedBalanceXlsxWriter(fields, tree.count, direction=direction) as writer:
            summary = data_service.get_period_summary(tree)
            header_end_row = writer.write_metadata(ctx, data_service, summary)

            x, y = header_end_row, 0
            for group_name, group in tree.children.items():
                x, y = writer.write_group(x, y, group_name, group, gathered['opening_balances'])

        return writer.value

    # ------------------------------------------------------------------
    # Ledger Balance (all-partners summary)
    # ------------------------------------------------------------------

    def _get_ledger_balance_records(self):
        return request.env['account.ledger.balance'].search([
            ('company_id', 'in', request.env.companies.ids)
        ])

    @http.route('/web/ledger_balance_export/xlsx', type='http', auth="user")
    def ledger_balance_export(self):
        records = self._get_ledger_balance_records()
        currency = request.env.company.currency_id
        lang, direction = DirectionResolver.for_summary_report(request.env)

        with LedgerBalanceXlsxWriter(currency.name, len(records), direction=direction) as writer:
            writer.write_records(records)

        filename = self._build_summary_filename('Ledger Balance')
        return request.make_response(
            writer.value,
            headers=[
                ('Content-Type', self.content_type),
                ('Content-Disposition', content_disposition(filename + self.extension)),
            ]
        )

    @http.route('/web/ledger_balance_export/pdf', type='http', auth="user")
    def ledger_balance_export_pdf(self):
        records = self._get_ledger_balance_records()
        currency = request.env.company.currency_id
        lang, direction = DirectionResolver.for_summary_report(request.env)

        env = self._lang_env(lang)
        values = self._base_pdf_values(title=env._('Ledger Balance'), lang=lang, direction=direction)
        values.update({
            'balance_header': env._('Balance (%s)') % currency.name,
            'rows': [
                (rec.partner_id.name or '', format_pdf_value(request.env, rec.balance, lang, digits=currency.decimal_places))
                for rec in records
            ],
        })
        pdf_bytes = render_balance_pdf(
            request.env,
            'partner_balance.action_report_ledger_balance_summary',
            'partner_balance.report_ledger_balance_summary_document',
            values,
        )
        filename = self._build_summary_filename('Ledger Balance')
        return request.make_response(pdf_bytes, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename + '.pdf')),
        ])

    # ------------------------------------------------------------------
    # Aged Balance Summary (all-partners summary)
    # ------------------------------------------------------------------

    def _get_aged_balance_summary_records(self, params):
        allowed_company_ids = params.get('allowed_company_ids') or request.env.companies.ids
        domain = [('company_id', 'in', allowed_company_ids)]
        domain.extend(params.get('domain', []))
        try:
            return request.env['account.aged.balance.summary'].search(domain)
        except Exception as e:
            _logger.error("aged_balance_summary_export | search FAILED: %s", e)
            raise

    @http.route('/web/aged_balance_summary_export/xlsx', type='http', auth="user")
    def aged_balance_summary_export(self, data='{}'):
        params = json.loads(data)
        records = self._get_aged_balance_summary_records(params)
        currency = request.env.company.currency_id
        lang, direction = DirectionResolver.for_summary_report(request.env)

        with AgedSummaryXlsxWriter(currency.name, len(records), direction=direction) as writer:
            writer.write_records(records)

        filename = self._build_summary_filename('Aged Balance')
        return request.make_response(
            writer.value,
            headers=[
                ('Content-Type', self.content_type),
                ('Content-Disposition', content_disposition(filename + self.extension)),
            ]
        )

    @http.route('/web/aged_balance_summary_export/pdf', type='http', auth="user")
    def aged_balance_summary_export_pdf(self, data='{}'):
        params = json.loads(data)
        records = self._get_aged_balance_summary_records(params)
        currency = request.env.company.currency_id
        lang, direction = DirectionResolver.for_summary_report(request.env)

        env = self._lang_env(lang)
        values = self._base_pdf_values(title=env._('Aged Balance Summary'), lang=lang, direction=direction)
        digits = currency.decimal_places
        values.update({
            'total_header': env._('Total (%s)') % currency.name,
            'rows': [
                (
                    rec.partner_id.name or '',
                    format_pdf_value(request.env, rec.amount_current, lang, digits=digits),
                    format_pdf_value(request.env, rec.amount_1_30, lang, digits=digits),
                    format_pdf_value(request.env, rec.amount_31_60, lang, digits=digits),
                    format_pdf_value(request.env, rec.amount_61_90, lang, digits=digits),
                    format_pdf_value(request.env, rec.amount_91_120, lang, digits=digits),
                    format_pdf_value(request.env, rec.amount_older, lang, digits=digits),
                    format_pdf_value(request.env, rec.amount_total, lang, digits=digits),
                )
                for rec in records
            ],
        })
        pdf_bytes = render_balance_pdf(
            request.env,
            'partner_balance.action_report_aged_balance_summary',
            'partner_balance.report_aged_balance_summary_document',
            values,
        )
        filename = self._build_summary_filename('Aged Balance')
        return request.make_response(pdf_bytes, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename + '.pdf')),
        ])
