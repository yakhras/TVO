from odoo import fields, models

from .logistics_container import CONTAINER_STATE_SELECTION


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
