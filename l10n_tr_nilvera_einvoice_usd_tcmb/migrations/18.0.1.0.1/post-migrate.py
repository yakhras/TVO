import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fill the TCMB rate on existing invoices that have none (no re-post needed)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env['account.move'].search([
        ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
        ('state', '!=', 'cancel'),
        ('l10n_tr_tcmb_rate', 'in', (0.0, False)),
        ('company_id.l10n_tr_tcmb', '=', True),
    ])
    skipped = moves._l10n_tr_fill_tcmb_rate()
    _logger.info(
        "TCMB rate backfill: %s invoices checked, %s filled, %s skipped (no rate available).",
        len(moves), len(moves) - len(skipped), len(skipped),
    )
    if skipped:
        _logger.info("TCMB rate backfill skipped move ids: %s", skipped.ids)
