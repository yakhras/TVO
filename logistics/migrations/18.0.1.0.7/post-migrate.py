import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Re-apply the 18.0.1.0.1 backfill, which was skipped on databases whose
    recorded module version was already >= 18.0.1.0.1:
    - containers still stored with the removed container_type 'truck' get
      transport_unit 'truck' and container_type 'other';
    - 20ft/40ft containers without a transport unit get 'container', their
      container_type is kept.
    Then sync the stored related transport_unit on container lines (never
    done by 18.0.1.0.1)."""
    cr.execute("""
        UPDATE logistics_container
        SET transport_unit = 'container'
        WHERE container_type IN ('20', '40')
          AND transport_unit IS NULL
    """)
    _logger.info("logistics: set transport unit 'container' on %s containers", cr.rowcount)
    cr.execute("""
        UPDATE logistics_container
        SET transport_unit = 'truck',
            container_type = 'other'
        WHERE container_type = 'truck'
    """)
    _logger.info("logistics: converted %s truck containers", cr.rowcount)
    cr.execute("""
        UPDATE logistics_container_line l
        SET transport_unit = c.transport_unit
        FROM logistics_container c
        WHERE c.id = l.container_id
          AND l.transport_unit IS DISTINCT FROM c.transport_unit
    """)
    _logger.info("logistics: synced transport unit on %s container lines", cr.rowcount)
