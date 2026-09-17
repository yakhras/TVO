# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class ArmongatePermissionController(http.Controller):

    @http.route('/armongate/apply_permission', type='http', auth='user')
    def apply_permission(self, config_id, unique_id, fullname, date, reason, **kwargs):
        config = request.env['armongate.config'].browse(int(config_id)).exists()
        if not config:
            return request.not_found()
        submission_id = config.submit_jotform_permission(unique_id, fullname, date, reason)
        return request.redirect(
            'https://www.jotform.com/edit/%s' % submission_id, local=False)
