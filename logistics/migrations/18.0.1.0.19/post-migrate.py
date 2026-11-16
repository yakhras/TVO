import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """EETA is now the Arriving Date when set, otherwise Readiness Date + 75
    days. Only the compute's dependencies changed, so Odoo does not recompute
    the stored values: backfill containers, then sync the stored related EETA
    on container lines."""
    cr.execute("""
        UPDATE logistics_container
        SET eeta_date = COALESCE(arrival_date, readiness_date + 75)
        WHERE eeta_date IS DISTINCT FROM COALESCE(arrival_date, readiness_date + 75)
    """)
    _logger.info("logistics: recomputed EETA on %s containers", cr.rowcount)
    cr.execute("""
        UPDATE logistics_container_line l
        SET eeta_date = c.eeta_date
        FROM logistics_container c
        WHERE c.id = l.container_id
          AND l.eeta_date IS DISTINCT FROM c.eeta_date
    """)
    _logger.info("logistics: synced EETA on %s container lines", cr.rowcount)
