def migrate(cr, version):
    """child_state_id became required: give every container whose child state
    is missing or belongs to another state the first child state (model
    _order: parent_state, child_state) of its own state, then sync the stored
    related copy on container lines.

    Mismatches are fixed too (not only NULLs) because, when the NOT NULL
    constraint is added, the ORM fills NULLs with the field default (first
    'purchase' child state) before this script runs.
    """
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
          );
    """)
    cr.execute("""
        UPDATE logistics_container_line l
        SET child_state_id = c.child_state_id
        FROM logistics_container c
        WHERE c.id = l.container_id
          AND l.child_state_id IS DISTINCT FROM c.child_state_id;
    """)
