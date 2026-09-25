from odoo import fields, models

# Defined here (not in logistics_container) so this model is registered, and
# its table created, before logistics.container: the container's required
# child_state_id default queries this table when the column is initialized.
CONTAINER_STATE_SELECTION = [
    ('purchase', 'Purchasing'),
    ('oversea', 'Oversea'),
    ('at_port', 'At Port'),
    ('arrived', 'Arrived'),
    ('antrepo', 'Antrepo'),
]


class LogisticsContainerChildState(models.Model):
    _name = 'logistics.container.child.state'
    _description = 'Container Child State'
    _order = 'parent_state, child_state'
    _rec_name = 'child_state'

    child_state = fields.Char(string='Child State', required=True)
    parent_state = fields.Selection(
        selection=CONTAINER_STATE_SELECTION,
        string='Parent State', required=True,
    )
    active = fields.Boolean(default=True)
