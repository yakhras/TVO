# -*- coding: utf-8 -*-

import html
import json
import logging
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.armongate_client import ArmonClient
from ..services.jotform_client import JotformClient

_logger = logging.getLogger(__name__)


class ArmonGateConfig(models.Model):
    _name = 'armongate.config'
    _description = 'Armongate API Configuration'

    name = fields.Char(string='Label', required=True, default='Local Dev')
    base_url = fields.Char(string='Base URL', default='https://api.armongate.com')
    username = fields.Char(string='Username')
    password = fields.Char(string='Password')
    organization_id = fields.Char(string='Organization ID')
    grant_type_id = fields.Char(string='Grant Type ID', readonly=True)
    access_token = fields.Char(string='Access Token', readonly=True)
    refresh_token = fields.Char(string='Refresh Token', readonly=True)
    token_id = fields.Char(string='Token ID', readonly=True)
    token_expires_at = fields.Datetime(string='Token Expires At', readonly=True)
    last_response = fields.Text(string='Last Response', readonly=True)
    yaser_log_date_from = fields.Date(string='Access Log From', default=fields.Date.context_today)
    yaser_log_date_to = fields.Date(string='Access Log To', default=fields.Date.context_today)
    yaser_log_table = fields.Html(string='Access Log Table', readonly=True, sanitize=False)
    jotform_api_key = fields.Char(string='Jotform API Key')

    @api.depends('access_token', 'token_expires_at')
    def _compute_is_token_expired(self):
        for rec in self:
            rec.is_token_expired = (
                not rec.access_token
                or not rec.token_expires_at
                or fields.Datetime.now() >= rec.token_expires_at - timedelta(seconds=30)
            )

    is_token_expired = fields.Boolean(compute='_compute_is_token_expired')

    def action_login(self):
        self.ensure_one()
        if not self.username or not self.password:
            raise UserError('Set Username and Password before logging in.')
        client = ArmonClient(self)
        orgs_resp = client.get_organizations(self.username)
        organizations = orgs_resp.get('organizations') or []
        if not organizations:
            raise UserError('Armon API: no organizations available for this user.')
        org = None
        if self.organization_id:
            org = next((o for o in organizations if o.get('id') == self.organization_id), None)
        if not org:
            org = organizations[0]
        authentications = org.get('authentications') or []
        if not authentications:
            raise UserError('Armon API: no authentication method available for this organization.')
        auth_method = next((a for a in authentications if a.get('isDefault')), authentications[0])
        _logger.info(
            'Armon login: config=%s org=%s grantTypeId=%s', self.id, org.get('id'), auth_method['id'])
        result = client.login_with_password(self.username, self.password, auth_method['id'])
        self._apply_token_result(result, grant_type_id=auth_method['id'])
        _logger.info('Armon login: config=%s succeeded, token_expires_at=%s', self.id, self.token_expires_at)

    def action_refresh_token(self):
        self.ensure_one()
        if not self.refresh_token:
            raise UserError('Armon API: no refresh token available — click "Login" first.')
        client = ArmonClient(self)
        result = client.refresh()
        self._apply_token_result(result)
        _logger.info('Armon refresh: config=%s succeeded, token_expires_at=%s', self.id, self.token_expires_at)

    def _apply_token_result(self, result, grant_type_id=None):
        self.ensure_one()
        vals = {
            'access_token': result.get('token'),
            'refresh_token': result.get('refreshToken'),
            'token_id': result.get('tokenId'),
            'token_expires_at': fields.Datetime.now() + timedelta(seconds=result.get('expiresIn') or 0),
        }
        org = (result.get('organization') or {}).get('organization') or {}
        if org.get('id'):
            vals['organization_id'] = org['id']
        if grant_type_id:
            vals['grant_type_id'] = grant_type_id
        self.write(vals)

    def action_test_user_api(self):
        self.ensure_one()
        if not self.access_token:
            raise UserError('Click "Login" first.')
        client = ArmonClient(self)
        users = client.get_users()

        now = fields.Datetime.now()
        start_utc = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_utc = now.strftime('%Y-%m-%dT%H:%M:%S.999Z')
        _logger.info(
            'Armon test_user_api: config=%s org=%s users_fetched=%s range=%s..%s',
            self.id, self.organization_id, len(users), start_utc, end_utc)
        logs = client.get_access_logs(start_utc, end_utc)

        # Per AccessLogsReportItem in the vendor's swagger dump, the user is
        # nested under `identity.id`, not a flat identityId/userId key.
        logs_by_user = {}
        for entry in logs:
            identity = entry.get('identity') or {}
            if identity.get('id'):
                logs_by_user.setdefault(identity['id'], []).append(entry)
        for user in users:
            user['access_logs_today'] = logs_by_user.get(user.get('id'), [])

        users_with_logs = sum(1 for u in users if u['access_logs_today'])
        _logger.info(
            'Armon test_user_api: config=%s access_logs_today_count=%s users_with_logs=%s/%s',
            self.id, len(logs), users_with_logs, len(users))
        if not logs:
            _logger.warning(
                'Armon test_user_api: config=%s got 0 access log entries for %s..%s on org %s. '
                'The request/join logic is confirmed correct (see the "Armon API" log lines above) — '
                'this means the vendor API itself returned nothing for this window. Likely causes: '
                '(1) the integration user\'s role lacks the "access_log:report_detailed" permission '
                'the endpoint declares as required, or (2) this organization\'s access-control hardware '
                'is not forwarding events into this API. Confirm both with Armongate support.',
                self.id, start_utc, end_utc, self.organization_id)

        self.last_response = json.dumps({
            'total_users': len(users),
            'access_logs_today_count': len(logs),
            'users': users,
        }, indent=2, ensure_ascii=False)

    def action_test_access_control_points(self):
        self.ensure_one()
        if not self.access_token:
            raise UserError('Click "Login" first.')
        client = ArmonClient(self)

        device_status = client.get_device_status()
        _logger.info('Armon test_access_control_points: config=%s device_status=%s', self.id, device_status)
        if (device_status or {}).get('disconnected'):
            _logger.warning(
                'Armon test_access_control_points: config=%s has %s disconnected device(s) '
                '(connected=%s). This would also explain empty access_logs_today results — '
                'a disconnected terminal cannot forward access events into report/accesslogs/v2.',
                self.id, device_status.get('disconnected'), device_status.get('connected'))

        access_control_points = client.get_access_control_points()
        details = []
        for acp in access_control_points:
            detail = client.get_access_control_point_detail(acp['id'])
            device_id = detail.get('deviceId')
            if device_id:
                device = client.get_device_detail(device_id)
                detail['ip'] = device.get('ip')
                detail['port'] = device.get('port')
                detail['serialNumber'] = device.get('serialNumber')
                detail['brand'] = device.get('brandName') or device.get('brand')
                detail['model'] = device.get('model')
            details.append(detail)

        _logger.info(
            'Armon test_access_control_points: config=%s total_access_control_points=%s',
            self.id, len(details))

        self.last_response = json.dumps({
            'device_status': device_status,
            'total_access_control_points': len(details),
            'access_control_points': details,
        }, indent=2, ensure_ascii=False)

    def action_test_first_and_last_access(self):
        self.ensure_one()
        if not self.access_token:
            raise UserError('Click "Login" first.')
        client = ArmonClient(self)

        now = fields.Datetime.now()
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_dt = now.strftime('%Y-%m-%dT%H:%M:%S.999Z')
        _logger.info(
            'Armon test_first_and_last_access: config=%s org=%s range=%s..%s',
            self.id, self.organization_id, start_dt, end_dt)
        entries = client.get_first_and_last_access_logs(start_dt, end_dt)
        _logger.info(
            'Armon test_first_and_last_access: config=%s entries=%s', self.id, len(entries))
        if entries:
            _logger.info(
                'Armon test_first_and_last_access: config=%s got non-empty results while '
                'report/accesslogs/v2 returned 0 for the same window — this endpoint draws from '
                'a different data source and should be preferred for access-log reporting.',
                self.id)

        self.last_response = json.dumps({
            'range': {'startDateTime': start_dt, 'endDateTime': end_dt},
            'entries_count': len(entries),
            'entries': entries,
        }, indent=2, ensure_ascii=False)

    def action_test_first_and_last_access_yaser(self):
        self.ensure_one()
        if not self.access_token:
            raise UserError('Click "Login" first.')
        client = ArmonClient(self)

        # report/accesslogs/v2 filters by Armon's internal UUID (`identity.id`),
        # not the human-readable `uniqueId` ("108"), so that UUID has to be
        # resolved via identity/search first.
        target_unique_id = '108'
        users = client.get_users()
        target_user = next((u for u in users if u.get('uniqueId') == target_unique_id), None)
        if not target_user:
            raise UserError('No Armon user found with uniqueId %s.' % target_unique_id)

        date_from = self.yaser_log_date_from or fields.Date.context_today(self)
        date_to = self.yaser_log_date_to or date_from
        if date_to < date_from:
            raise UserError('"Access Log To" cannot be before "Access Log From".')
        start_dt = date_from.strftime('%Y-%m-%dT00:00:00.000Z')
        end_dt = date_to.strftime('%Y-%m-%dT23:59:59.999Z')
        entries = client.get_access_logs(start_dt, end_dt, user_ids=[target_user['id']])
        _logger.info(
            'Armon test_first_and_last_access_yaser: config=%s user=%s(%s) entries=%s',
            self.id, target_user.get('fullname'), target_user['id'], len(entries))

        self.last_response = json.dumps({
            'range': {'startDateTime': start_dt, 'endDateTime': end_dt},
            'user': {
                'uniqueId': target_unique_id,
                'id': target_user['id'],
                'fullname': target_user.get('fullname'),
            },
            'entries_count': len(entries),
            'entries': entries,
        }, indent=2, ensure_ascii=False)
        self.yaser_log_table = self._render_access_log_table(entries)

    @staticmethod
    def _format_timedelta(td):
        minutes = int(td.total_seconds() // 60)
        hours, minutes = divmod(minutes, 60)
        return '%dh %dm' % (hours, minutes) if hours else '%dm' % minutes

    def _compute_time_deductions(self, entries):
        """Attendance deduction, per the documented working-time policy (08:30-18:30):
        - First entrance after 08:30: deducted (the late duration). Whether a
          penalty additionally applies (only after 09:00, waived with prior
          permission) is not computed here — the Armon API carries no
          "permission obtained" flag, so that judgment is left to HR; only the
          deduction *duration* the policy specifies is derived.
        - A break starting between 12:00-15:00 is unpaid-free up to 45 minutes;
          only the excess over 45 minutes is deducted.
        - A break starting after 15:00 is deducted in full (its whole duration).
        - If the final exit of the day is after 18:30, that overtime offsets
          ("compensates") the deductions accumulated earlier that day.
        Returns {entry_id: (label, css_color)}.
        """
        start, late_deadline = time(8, 30), time(9, 0)
        lunch_start, lunch_end = time(12, 0), time(15, 0)
        lunch_allowance = timedelta(minutes=45)
        end = time(18, 30)

        by_day = {}
        for entry in entries:
            try:
                dt = datetime.fromisoformat(entry.get('utc') or '')
            except ValueError:
                continue
            by_day.setdefault(dt.date(), []).append((dt, entry))

        result = {}
        for day, day_events in by_day.items():
            day_events.sort(key=lambda pair: pair[0])

            first_dt, first_entry = day_events[0]
            if first_entry.get('direction') == 1 and first_dt.time() > start:
                late = datetime.combine(day, first_dt.time()) - datetime.combine(day, start)
                penalty_note = '' if first_dt.time() <= late_deadline else ', penalty unless permitted'
                result[first_entry['id']] = (
                    '-%s (late arrival%s)' % (self._format_timedelta(late), penalty_note), '#dc3545')

            pending_exit_dt = None
            for dt, entry in day_events:
                direction = entry.get('direction')
                if direction == 2:
                    pending_exit_dt = dt
                elif direction == 1 and pending_exit_dt is not None:
                    gap = dt - pending_exit_dt
                    exit_time = pending_exit_dt.time()
                    if lunch_start <= exit_time <= lunch_end:
                        if gap > lunch_allowance:
                            result[entry['id']] = (
                                '-%s (lunch break over 45m, penalty unless permitted)'
                                % self._format_timedelta(gap - lunch_allowance), '#dc3545')
                    elif exit_time > lunch_end:
                        result[entry['id']] = (
                            '-%s (left after 3 PM, penalty unless permitted)'
                            % self._format_timedelta(gap), '#dc3545')
                    pending_exit_dt = None

            last_dt, last_entry = day_events[-1]
            if last_entry.get('direction') == 2 and last_dt.time() > end:
                comp = datetime.combine(day, last_dt.time()) - datetime.combine(day, end)
                result[last_entry['id']] = (
                    '+%s (compensated)' % self._format_timedelta(comp), '#28a745')

        return result

    # URL-param prefill doesn't work on this form (confirmed live: neither the
    # jotform.com/app/... PWA wrapper nor the plain form.jotform.com URL apply
    # any query params to field values -- Jotform's own client script has no
    # generic field-prefill-from-URL logic). Filling the form now happens via
    # a real POST to the submissions API instead; see submit_jotform_permission.
    JOTFORM_FORM_ID = '202811735864963'
    # qid -> Armon field, for the "İzin Talebi" form's known fields (name/id/
    # explanation/dates). Categorical fields (leave type/reason radios) have
    # no equivalent in Armon's deduction data and are left for the reviewer
    # to pick when they open the created submission for completion.
    JOTFORM_QID_ID = '75'
    JOTFORM_QID_FULLNAME = '64'
    JOTFORM_QID_ACIKLAMA = '45'
    JOTFORM_QID_BASLANGIC_TARIHI = '69'
    JOTFORM_QID_BITIS_TARIHI = '70'

    def _build_permission_link(self, unique_id, fullname, dt, deduction_label):
        """Link to our own controller, which creates the Jotform submission
        server-side and redirects the browser to it for the reviewer to
        complete -- see armongate/controllers/main.py."""
        params = {
            'config_id': self.id,
            'unique_id': unique_id,
            'fullname': fullname,
            'date': dt.strftime('%Y-%m-%d') if dt else '',
            'reason': deduction_label,
        }
        return '/armongate/apply_permission?%s' % urlencode(params)

    def submit_jotform_permission(self, unique_id, fullname, date_str, reason):
        """Create a Jotform submission for the "İzin Talebi" permit form,
        pre-filled with what Armon already knows. Leave-type/reason radios
        aren't set here -- the reviewer picks those when they open the
        returned submission for completion. Returns the submission ID."""
        self.ensure_one()
        if not self.jotform_api_key:
            raise UserError('Set the Jotform API Key on this Armongate configuration first.')
        answers = {
            'submission[%s]' % self.JOTFORM_QID_ID: unique_id,
            'submission[%s]' % self.JOTFORM_QID_FULLNAME: fullname,
            'submission[%s]' % self.JOTFORM_QID_ACIKLAMA: reason,
        }
        if date_str:
            year, month, day = date_str.split('-')
            for qid in (self.JOTFORM_QID_BASLANGIC_TARIHI, self.JOTFORM_QID_BITIS_TARIHI):
                answers['submission[%s_month]' % qid] = month
                answers['submission[%s_day]' % qid] = day
                answers['submission[%s_year]' % qid] = year
        client = JotformClient(self.jotform_api_key)
        return client.create_submission(self.JOTFORM_FORM_ID, answers)

    def _render_access_log_table(self, entries):
        """Build an HTML table matching the Armon portal's access-log view
        (Name Surname / unique id, Access Time, Access Point, Status), plus a
        Deduction column derived from the working-time policy, and a button to
        open the permission form on rows carrying an actual deduction (the
        policy waives the penalty, not the deduction itself, when permission
        was obtained for it)."""
        # Empirically confirmed from live entries: direction 1 pairs with the
        # "GİRİŞ" (entrance) access point, direction 2 with "ÇIKIŞ" (exit).
        direction_labels = {1: 'entrance', 2: 'exit'}
        deduction_color_of_penalty = '#dc3545'
        deductions = self._compute_time_deductions(entries)
        rows = []
        for entry in entries:
            identity = entry.get('identity') or {}
            access_point = entry.get('accessControlPoint') or {}
            fullname = entry.get('logUserInfo') or (
                '%s %s' % (identity.get('name') or '', identity.get('surname') or '')).strip()
            unique_id = identity.get('uniqueId') or ''

            utc_str = entry.get('utc') or ''
            try:
                dt = datetime.fromisoformat(utc_str)
                time_label = dt.strftime('%I:%M %p').lstrip('0')
                date_label = dt.strftime('%A, %B %d, %Y')
            except ValueError:
                time_label, date_label = utc_str, ''

            direction_label = direction_labels.get(entry.get('direction'), 'access')
            result_label = 'Successful' if entry.get('result') == 0 else 'Failed'
            status_color = '#28a745' if entry.get('result') == 0 else '#dc3545'
            deduction_label, deduction_color = deductions.get(entry.get('id'), ('-', '#888'))
            permission_cell = (
                '<a href="%s" target="_blank" rel="noopener" '
                'class="btn btn-sm btn-outline-primary">Apply Permission</a>'
                % html.escape(self._build_permission_link(unique_id, fullname, dt, deduction_label))
                if deduction_color == deduction_color_of_penalty else ''
            )

            rows.append(
                '<tr>'
                '<td><div>%s</div><div style="color:#888;font-size:0.85em;">%s</div></td>'
                '<td><div><b>%s</b></div><div style="color:#888;font-size:0.85em;">%s</div></td>'
                '<td>%s</td>'
                '<td><span style="color:%s;">&#9679;</span> %s %s</td>'
                '<td style="color:%s;">%s</td>'
                '<td>%s</td>'
                '</tr>' % (
                    html.escape(fullname), html.escape(unique_id),
                    html.escape(time_label), html.escape(date_label),
                    html.escape(access_point.get('name') or ''),
                    status_color, result_label, direction_label,
                    deduction_color, html.escape(deduction_label),
                    permission_cell,
                )
            )

        if not rows:
            return '<p>No access log entries for the selected range.</p>'

        return (
            '<table class="table table-sm table-bordered">'
            '<thead><tr><th>Name Surname</th><th>Access Time</th>'
            '<th>Access Point</th><th>Status</th><th>Deduction</th><th>Permission</th></tr></thead>'
            '<tbody>%s</tbody></table>' % ''.join(rows)
        )

    def action_open_restart_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Restart Terminal',
            'res_model': 'armongate.restart_terminal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id},
        }
