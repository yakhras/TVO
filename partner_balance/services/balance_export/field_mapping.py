# -*- coding: utf-8 -*-
"""Field mapping to replace magic column indices."""


class FieldMapping:
    """Maps field names to column indices for balance exports."""

    # Standard column layout for balance reports
    COLUMNS = {
        'date': 0,
        'journal_entry': 1,
        'label': 2,
        'reference': 3,
        'debit': 4,
        'credit': 5,
        'balance': 6,
        'cumulated_balance': 6,
        'amount_currency': 7,
        'currency': 8,
    }

    # Aliases for different naming conventions
    ALIASES = {
        'debit_amount': 'debit',
        'credit_amount': 'credit',
        'balance_amount': 'balance',
        'note': 'reference',
        'type': 'journal_entry',
    }

    # TRY report column layout
    COLUMNS_TR = {
        'date': 0,
        'journal_entry': 1,
        'label': 2,
        'reference': 3,
        'debit': 4,
        'credit': 5,
        'balance': 6,
        'cumulated_balance': 6,
        'amount_currency': 7,
        'rate': 8,
        'currency': 9,
    }

    @classmethod
    def get_columns(cls, is_tr_report=False):
        """Return the appropriate column mapping."""
        return cls.COLUMNS_TR if is_tr_report else cls.COLUMNS

    @classmethod
    def get_index(cls, field_name):
        """Get column index for a field name."""
        normalized = cls.ALIASES.get(field_name, field_name)
        return cls.COLUMNS.get(normalized)

    @classmethod
    def get_value(cls, row, field_name):
        """Get value from row by field name."""
        idx = cls.get_index(field_name)
        if idx is not None and idx < len(row):
            return row[idx]
        return None

    @classmethod
    def set_value(cls, row, field_name, value):
        """Set value in row by field name. Row must be a list."""
        idx = cls.get_index(field_name)
        if idx is not None and idx < len(row):
            row[idx] = value

    @classmethod
    def get_numeric_value(cls, row, field_name, default=0.0):
        """Get numeric value from row, converting if necessary."""
        value = cls.get_value(row, field_name)
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        return default

    @classmethod
    def create_opening_balance_row(cls, opening_data, env=None):
        """Create a standard opening balance row.

        `env` lets callers translate "Opening Balance" into a specific report
        language: the bare `_()` helper resolves its language by inspecting the
        caller's frame, which is unreliable across module boundaries, so pass an
        env already scoped to the target `lang` (see `env(context=...)`) when the
        report language may differ from the current request's own session language.
        """
        from odoo.tools.translate import _

        row = [''] * 9
        row[cls.COLUMNS['date']] = opening_data.get('date', '')
        row[cls.COLUMNS['journal_entry']] = ''
        row[cls.COLUMNS['label']] = env._('Opening Balance') if env is not None else _('Opening Balance')
        row[cls.COLUMNS['reference']] = ''
        row[cls.COLUMNS['debit']] = opening_data.get('debit', 0.0)
        row[cls.COLUMNS['credit']] = opening_data.get('credit', 0.0)
        row[cls.COLUMNS['balance']] = opening_data.get('balance', 0.0)
        row[cls.COLUMNS['amount_currency']] = ''
        row[cls.COLUMNS['currency']] = ''
        return row

    @staticmethod
    def get_max_decimal_places(env):
        """Get maximum decimal places across installed currencies (shared by the
        xlsx and PDF export pipelines so they show the same precision)."""
        try:
            results = env['res.currency'].search_read([], ['decimal_places'])
            places = [r['decimal_places'] for r in results]
            return max(places) if places else 2
        except Exception:
            return 2

    @classmethod
    def find_column_by_label(cls, fields, partial_name):
        """Find column index by partial field label match."""
        partial_lower = partial_name.lower()
        for idx, field in enumerate(fields):
            label = field if isinstance(field, str) else field.get('label', '')
            if partial_lower in label.lower():
                return idx
        return None
