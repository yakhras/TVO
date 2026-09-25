import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Databases upgraded from before child states existed get the default
    child states from data/container_child_states.xml only after the
    required child_state_id column was added, so their containers are still
    empty and NOT NULL could not be set. Give every container without a
    valid child state the first child state of its own state, sync the
    stored copy on container lines, then enforce NOT NULL."""
    cr.execute("""
        WITH first_child AS (
            SELECT DISTINCT ON (parent_state) parent_state, id
            FROM logistics_container_child_state
            WHERE active
            ORDER BY parent_state, child_state, id
        )
        UPDATE logistics_container c
        SET child_state_id = fc.id
        FROM first_child fc
        WHERE fc.parent_state = c.state
          AND NOT EXISTS (
              SELECT 1 FROM logistics_container_child_state cs
              WHERE cs.id = c.child_state_id
                AND cs.parent_state = c.state
          )
    """)
    _logger.info("logistics: set child state on %s containers", cr.rowcount)
    cr.execute("""
        UPDATE logistics_container_line l
        SET child_state_id = c.child_state_id
        FROM logistics_container c
        WHERE c.id = l.container_id
          AND l.child_state_id IS DISTINCT FROM c.child_state_id
    """)
    cr.execute("SELECT COUNT(*) FROM logistics_container WHERE child_state_id IS NULL")
    missing = cr.fetchone()[0]
    if missing:
        _logger.warning(
            "logistics: %s containers still have no child state, NOT NULL not set", missing,
        )
    else:
        sql.set_not_null(cr, 'logistics_container', 'child_state_id')
