# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError

from ..services.armongate_client import ArmonClient


class ArmonGateRestartTerminalWizard(models.TransientModel):
    _name = 'armongate.restart_terminal.wizard'
    _description = 'Restart an Armongate door terminal (physical action — confirm before use)'

    config_id = fields.Many2one('armongate.config', string='Configuration', required=True)
    device_id = fields.Char(
        string='Device ID',
        required=True,
        help='The deviceId of the terminal to restart (see "Access Control Points" in Test Access Points output).')

    def action_confirm(self):
        self.ensure_one()
        if not self.config_id.access_token:
            raise UserError('Click "Login" on the configuration first.')
        client = ArmonClient(self.config_id)
        client.restart_terminal(self.device_id)
