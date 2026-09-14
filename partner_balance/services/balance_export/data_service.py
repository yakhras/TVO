# -*- coding: utf-8 -*-
"""Data fetching and calculation service for balance exports."""

import datetime
from datetime import timedelta

from .field_mapping import FieldMapping
from ...constants import ReportConstants


class BalanceDataService:
    """Handles all data fetching and calculations for balance exports."""

    def __init__(self, env, partner_id, date_from=None, date_to=None, is_tr_report=False):
        self.env = env
        self.partner_id = partner_id
        self.date_from = date_from
        self.date_to = date_to
        self.is_tr_report = is_tr_report
        self._model = env['account.move.line.report']

    @classmethod
    def from_params(cls, env, params):
        """Factory method to create service from request params."""
        ctx = params.get('context', {})
        return cls(
            env=env,
            partner_id=ctx.get('default_partner_id'),
            date_from=ctx.get('date_from'),
            date_to=ctx.get('date_to'),
            is_tr_report=ctx.get('action_name') == 'Statement in TRY',
        )

    def _zero_balance(self, currency=None):
        """Return zero balance dict."""
        return {
            'debit': 0.0,
            'credit': 0.0,
            'balance': 0.0,
            'currency': currency or ReportConstants.CURRENCY_TRY,
            'date': '',
        }

    def _opening_date(self):
        """Calculate opening balance date (day before date_from)."""
        if not self.date_from:
            return ''
        date_obj = datetime.datetime.strptime(self.date_from, '%Y-%m-%d')
        return (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')

    def _base_domain(self):
        """Base domain for partner queries."""
        return [
            ('partner_id', '=', self.partner_id),
            ('move_id.journal_id.code', 'not in', ReportConstants.EXCLUDED_JOURNAL_CODES),
        ]

    def get_opening_balance(self, filter_field=None, filter_value=None):
        """Delegate to the model's unified get_opening_balance_value method.

        When called without filter args, the model returns a per-currency dict
        for toolbar display. This method aggregates it into the flat
        {debit, credit, balance, currency, date} format that export consumers expect.
        """
        if not self.date_from or not self.partner_id:
            currency = filter_value if filter_field == 'currency_id.name' else ReportConstants.CURRENCY_TRY
            return self._zero_balance(currency)

        result = self._model.get_opening_balance_value(
            self.partner_id,
            self.date_from,
            is_tr_report=self.is_tr_report,
            filter_field=filter_field,
            filter_value=filter_value,
        )

        # Filtered calls already return the flat format — pass through
        if filter_field is not None:
            return result

        # Unfiltered calls return per-currency dict: {'TRY': {'opening': ..., ...}}
        # Aggregate into the flat format consumers expect
        total_debit = 0.0
        total_credit = 0.0
        currency = ReportConstants.CURRENCY_TRY
        for curr_name, vals in result.items():
            total_debit += vals.get('debit', 0.0)
            total_credit += vals.get('credit', 0.0)
            currency = curr_name  # last currency wins; typically single-company

        return {
            'debit': total_debit,
            'credit': total_credit,
            'balance': total_debit - total_credit,
            'currency': currency,
            'date': self._opening_date(),
        }


    def get_period_summary(self, rows):
        """
        Calculate period summary totals.

        Args:
            rows: List of data rows or GroupsTreeNode
        """
        opening_data = self.get_opening_balance()
        running_balance = opening_data['balance']
        total_debit = 0.0
        total_credit = 0.0

        all_rows = self._extract_rows(rows)

        for row in all_rows:
            debit = FieldMapping.get_numeric_value(row, 'debit')
            credit = FieldMapping.get_numeric_value(row, 'credit')
            running_balance += debit - credit
            total_debit += debit
            total_credit += credit

        return {
            'opening_balance': opening_data['balance'],
            'closing_balance': running_balance,
            'period_movement': total_debit - total_credit,
            'total_debit': total_debit,
            'total_credit': total_credit,
        }

    def _extract_rows(self, data):
        """Extract rows from either list or GroupsTreeNode."""
        if hasattr(data, 'children'):
            return self._extract_rows_from_groups(data)
        return data

    def _extract_rows_from_groups(self, groups_node):
        """Recursively extract all data rows from GroupsTreeNode."""
        rows = []
        if hasattr(groups_node, 'data') and groups_node.data:
            rows.extend(groups_node.data)
        if hasattr(groups_node, 'children'):
            for child in groups_node.children.values():
                rows.extend(self._extract_rows_from_groups(child))
        return rows

    def get_oldest_date(self, env=None):
        """Get the oldest transaction date for the partner.

        `env` lets callers translate "Beginning" into a specific report language
        (see `FieldMapping.create_opening_balance_row` for why the bare `_()`
        helper isn't reliable here); defaults to `self.env`'s own language.
        """
        translate = (env or self.env)._
        if not self.partner_id:
            return translate('Beginning')

        result = self.env['account.move.line'].sudo().read_group(
            domain=[('partner_id', '=', self.partner_id)],
            fields=['date:min'],
            groupby=[],
        )

        if result and result[0].get('date'):
            return result[0]['date']
        return translate('Beginning')

    def get_opening_balances_by_group(self, groups, groupby_field, use_partner_currency=False):
        """
        Calculate opening balances for each group.

        Args:
            groups: GroupsTreeNode with children
            groupby_field: Field used for grouping (e.g., 'currency_id')
            use_partner_currency: Use partner currency calculations
        """
        opening_balances = {}

        for group_name in groups.children.keys():
            filter_field = None
            filter_value = None

            if groupby_field == 'currency_id':
                filter_field = 'currency_id.name'
                filter_value = group_name[1] if isinstance(group_name, tuple) else group_name
            elif groupby_field == 'account_id':
                filter_field = 'account_id.id'
                filter_value = group_name[0] if isinstance(group_name, tuple) else group_name

            opening_data = self.get_opening_balance(filter_field, filter_value)
            opening_balances[group_name] = opening_data

        return opening_balances

    def update_group_running_balances(self, groups, opening_balances):
        """Update cumulated balances in group data with opening balances."""
        for group_name, group in groups.children.items():
            currency_key = group_name[1] if isinstance(group_name, tuple) else group_name
            self._update_group_recursive(group, opening_balances, currency_key)

    def _update_group_recursive(self, group_node, opening_balances, currency_key):
        """Recursively update running balance for a group."""
        opening_balance = opening_balances.get(currency_key, {}).get('balance', 0.0)
        running_balance = opening_balance

        for record in group_node.data:
            debit = FieldMapping.get_numeric_value(record, 'debit')
            credit = FieldMapping.get_numeric_value(record, 'credit')
            running_balance += debit - credit
            FieldMapping.set_value(record, 'balance', running_balance)

        for child in group_node.children.values():
            self._update_group_recursive(child, opening_balances, currency_key)
