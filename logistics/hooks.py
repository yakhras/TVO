def post_init_hook(env):
    """Backfill transport_unit from the legacy container_type value, then
    fold the removed 'truck' container_type option into 'other' (truck info
    now lives on transport_unit instead).
    """
    env.cr.execute("""
        UPDATE logistics_container
        SET transport_unit = CASE
            WHEN container_type = 'truck' THEN 'truck'
            WHEN container_type IN ('20', '40') THEN 'container'
            ELSE transport_unit
        END
        WHERE transport_unit IS NULL;
    """)
    env.cr.execute("""
        UPDATE logistics_container
        SET container_type = 'other'
        WHERE container_type = 'truck';
    """)
