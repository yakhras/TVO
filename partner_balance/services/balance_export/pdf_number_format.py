# -*- coding: utf-8 -*-
"""Locale-aware number formatting for the PDF export pipeline.

The PDF templates render pre-built Python values via bare QWeb `t-esc`, with no
field/widget layer (unlike the web client) and no cell `num_format` (unlike the
xlsx writer). So numeric values must already be formatted into their final,
locale-correct string before they reach the template.
"""

from markupsafe import Markup

from odoo.tools.misc import formatLang

from .direction_resolver import DirectionResolver

# Left-to-right mark: in an RTL page, a leading '-' has no strong direction and
# would be drawn after the digits ("1,234.00-"). Prefixing an LRM turns the
# whole number into one LTR run so the sign stays on the left.
LRM = '‎'


def format_pdf_value(env, value, lang, digits=2, currency=None):
    """Format a single numeric value using res.lang-aware formatLang().

    `currency` (a res.currency record) adds its symbol on the side given by
    its `position`. The symbol is attached manually rather than through
    formatLang(currency_obj=...), which would override `digits` with the
    currency's own precision and break column alignment with other numbers.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    env_for_lang = env(context=dict(env.context, lang=lang)) if lang else env
    formatted = formatLang(env_for_lang, value, digits=digits)
    if currency and currency.symbol:
        if currency.position == 'after':
            formatted = f'{formatted}\N{NO-BREAK SPACE}{currency.symbol}'
        else:
            formatted = f'{currency.symbol}\N{NO-BREAK SPACE}{formatted}'
    if DirectionResolver._direction_for_lang(env, lang) == 'rtl':
        # Trailing LRM too: a symbol placed after the number would otherwise
        # drift to the far (left) side in an RTL paragraph.
        formatted = LRM + formatted + LRM
    # wkhtmltopdf may wrap a narrow cell right after the '-', leaving the sign
    # and the digits on separate lines; keep the number on one line.
    return Markup('<span style="white-space:nowrap">%s</span>') % formatted


def format_pdf_row(env, row, numeric_indices, lang, digits=2):
    """Return a copy of `row` with values at `numeric_indices` formatted via
    formatLang(); other cells are passed through unchanged."""
    row = list(row)
    for idx in numeric_indices:
        if idx < len(row):
            row[idx] = format_pdf_value(env, row[idx], lang, digits=digits)
    return row
