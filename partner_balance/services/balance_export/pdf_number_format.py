# -*- coding: utf-8 -*-
"""Locale-aware number formatting for the PDF export pipeline.

The PDF templates render pre-built Python values via bare QWeb `t-esc`, with no
field/widget layer (unlike the web client) and no cell `num_format` (unlike the
xlsx writer). So numeric values must already be formatted into their final,
locale-correct string before they reach the template.
"""

from odoo.tools.misc import formatLang


def format_pdf_value(env, value, lang, digits=2):
    """Format a single numeric value using res.lang-aware formatLang()."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    env_for_lang = env(context=dict(env.context, lang=lang)) if lang else env
    return formatLang(env_for_lang, value, digits=digits)


def format_pdf_row(env, row, numeric_indices, lang, digits=2):
    """Return a copy of `row` with values at `numeric_indices` formatted via
    formatLang(); other cells are passed through unchanged."""
    row = list(row)
    for idx in numeric_indices:
        if idx < len(row):
            row[idx] = format_pdf_value(env, row[idx], lang, digits=digits)
    return row
