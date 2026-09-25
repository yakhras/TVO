from odoo.tools import sql

# xml id -> (child_state, parent_state), see data/container_child_states.xml
CHILD_STATES = {
    'child_state_waiting_loading_termin': ('Waiting for Loading Termin', 'purchase'),
    'child_state_awaiting_supplier_load': ('Awaiting Supplier Load', 'purchase'),
    'child_state_loading_port_waiting_departure': ('At Loading Port Waiting for Departure', 'purchase'),
    'child_state_on_the_way': ('On the Way', 'oversea'),
    'child_state_custom_clearance_destination_port': ('Custom Clerance at Destination Port', 'at_port'),
    'child_state_at_discharging_port': ('At Discharging Port', 'at_port'),
    'child_state_custom_clearance_loading_port': ('Custom Clerance at Loading Port', 'at_port'),
    'child_state_problem_custom_clearance': ('Problem at Custom Clerance', 'at_port'),
    'child_state_port_to_antrepo_transit': ('Port to Antrepo Transit', 'at_port'),
    'child_state_completed': ('Completed', 'arrived'),
    'child_state_syria_transit_stage': ('Syria Transit Stage', 'arrived'),
    'child_state_at_antrepo': ('At Antrepo', 'antrepo'),
}


def migrate(cr, version):
    """Child states used to be created by hand only. Link existing ones (same
    name and parent state) to the xml ids of data/container_child_states.xml
    so loading that file does not create duplicates."""
    if not sql.table_exists(cr, 'logistics_container_child_state'):
        return
    for xmlid, (child_state, parent_state) in CHILD_STATES.items():
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            SELECT 'logistics', %s, 'logistics.container.child.state', cs.id, true
            FROM logistics_container_child_state cs
            WHERE cs.child_state = %s AND cs.parent_state = %s
              AND NOT EXISTS (
                  SELECT 1 FROM ir_model_data
                  WHERE module = 'logistics' AND name = %s
              )
            ORDER BY cs.id
            LIMIT 1
        """, (xmlid, child_state, parent_state, xmlid))
