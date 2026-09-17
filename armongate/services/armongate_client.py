# -*- coding: utf-8 -*-

import logging

import requests
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_REDACT_KEYS = {'password', 'accessToken', 'refreshToken', 'token'}


def _redact(body):
    if not isinstance(body, dict):
        return body
    return {k: ('<redacted>' if k in _REDACT_KEYS else v) for k, v in body.items()}


class ArmonClient:
    def __init__(self, config):
        self.config = config
        self.base_url = config.base_url.rstrip('/')

    # -- low-level transport -------------------------------------------------
    def _request(self, method, path, body=None, auth=False):
        headers = {'Content-Type': 'application/json'}
        if auth:
            if not self.config.access_token:
                raise UserError('Armon API: not logged in yet — click "Login" first.')
            headers['Authorization'] = 'Bearer <redacted>'
            real_headers = dict(headers, Authorization='Bearer %s' % self.config.access_token)
        else:
            real_headers = headers
        _logger.info('Armon API request: %s %s body=%s', method, path, _redact(body))
        try:
            resp = requests.request(
                method, self.base_url + path, headers=real_headers, json=body, timeout=15)
        except requests.exceptions.Timeout:
            _logger.warning('Armon API request timed out: %s %s', method, path)
            raise UserError('Armon API request timed out.')
        except requests.exceptions.ConnectionError:
            _logger.warning('Armon API connection error: %s %s', method, path)
            raise UserError('Could not connect to Armon API.')
        return resp

    def _call(self, method, path, body=None, auth=False):
        resp = self._request(method, path, body=body, auth=auth)
        if resp.status_code == 401:
            _logger.warning('Armon API response: %s %s -> 401 unauthorized', method, path)
            raise UserError('Armon API error (401): unauthorized — check credentials/token.')
        if resp.status_code != 200:
            _logger.warning(
                'Armon API response: %s %s -> %s: %s', method, path, resp.status_code, resp.text[:500])
            raise UserError('Armon API error %s: %s' % (resp.status_code, resp.text[:500]))
        data = resp.json()
        if isinstance(data, dict) and 'items' in data:
            _logger.info(
                'Armon API response: %s %s -> 200, total=%s skip=%s take=%s items=%s',
                method, path, data.get('total'), data.get('skip'), data.get('take'), len(data.get('items') or []))
        else:
            _logger.info('Armon API response: %s %s -> 200', method, path)
        return data

    def _authed_call(self, method, path, body=None):
        """Ensure a fresh token before calling, and retry once on 401."""
        if self.config.is_token_expired:
            self.config.action_refresh_token()
        try:
            return self._call(method, path, body=body, auth=True)
        except UserError as exc:
            if '(401)' not in str(exc):
                raise
            self.config.action_refresh_token()
            return self._call(method, path, body=body, auth=True)

    # -- auth (see source_data/Login Authentication.pdf) ---------------------
    def get_organizations(self, username):
        return self._call('POST', '/auth/user', {'username': username})

    def login_with_password(self, username, password, grant_type_id):
        return self._call(
            'POST', '/auth/usernamepass/%s' % grant_type_id,
            {'username': username, 'password': password})

    def refresh(self):
        body = {
            'refreshToken': self.config.refresh_token,
            'organizationId': self.config.organization_id,
        }
        return self._call('POST', '/auth/refresh', body, auth=True)

    def logout(self):
        return self._call(
            'POST', '/service/auth/logout',
            {'grantTypeId': self.config.grant_type_id}, auth=True)

    def _paginate(self, path, body, take=100):
        """POST path repeatedly, bumping skip/take in body, until every item is collected."""
        items = []
        skip = 0
        while True:
            page_body = dict(body, skip=skip, take=take)
            page = self._authed_call('POST', path, page_body)
            page_items = page.get('items') or []
            items.extend(page_items)
            total = page.get('total', len(items))
            _logger.info(
                'Armon API pagination: %s skip=%s got=%s collected=%s/%s',
                path, skip, len(page_items), len(items), total)
            skip += take
            if not page_items or len(items) >= total:
                break
        return items

    # -- business (see source_data/API-Example.postman_collection.json) ------
    def get_users(self, profile_filter=None):
        body = {
            'status': 2,
            'organizationUnits': [],
            'userGroupIds': [],
        }
        if profile_filter:
            body['profileFilter'] = profile_filter
        path = '/u/v1/%s/identity/search' % self.config.organization_id
        return self._paginate(path, body)

    def get_access_logs(self, start_utc, end_utc, user_ids=None):
        body = {
            'dataIdentities': [],
            'dataOrganizationUnits': [],
            'dataAccessControlPoints': [],
            'dataUserGroups': [],
            'dateformatterPipe': {},
            'startUtc': start_utc,
            'endUtc': end_utc,
            'accessResult': 0,
            'direction': 0,
            'userIds': user_ids or [],
            'organizationUnitIds': [],
            'filterOrganizationUnitMembersHierarchically': False,
            'userGroupIds': [],
            'accessControlPointIds': [],
            'reasons': [],
            'returnTotalCount': True,
            'sortDateDesc': True,
        }
        path = '/u/v1/%s/report/accesslogs/v2' % self.config.organization_id
        _logger.info(
            'Armon API get_access_logs: org=%s startUtc=%s endUtc=%s userIds=%s',
            self.config.organization_id, start_utc, end_utc, user_ids or [])
        logs = self._paginate(path, body)
        _logger.info('Armon API get_access_logs: collected %s entries', len(logs))
        return logs

    # -- access control points (see source_data/data.xml) --------------------
    def get_device_status(self):
        path = '/u/v1/%s/device/status' % self.config.organization_id
        return self._authed_call('GET', path)

    def get_access_control_points(self):
        body = {'take': 100, 'skip': 0}
        path = '/u/v1/%s/accesscontrolpoint/genericsearch' % self.config.organization_id
        return self._paginate(path, body)

    def get_access_control_point_detail(self, acp_id):
        path = '/u/v1/%s/accesscontrolpoint/%s/detailed/v3' % (self.config.organization_id, acp_id)
        return self._authed_call('GET', path)

    def get_device_detail(self, device_id):
        path = '/u/v1/%s/device/%s/detailed' % (self.config.organization_id, device_id)
        return self._authed_call('GET', path)

    def restart_terminal(self, device_id):
        """Restarts a live door controller. Physical/hardware action — call with care."""
        path = '/u/v1/%s/terminals/%s/actions/restart' % (self.config.organization_id, device_id)
        _logger.warning('Armon API restart_terminal: org=%s device=%s', self.config.organization_id, device_id)
        return self._authed_call('POST', path)

    # -- alternate access-log source (see source_data/data.xml) --------------
    def get_first_and_last_access_logs(self, start_datetime, end_datetime, user_ids=None, take=100):
        """Per-user first/last access for the range. Different response envelope than
        report/accesslogs/v2 -- pagination is nested under `pagination`, not top-level."""
        path = '/u/v1/%s/firstandlastaccesslogsreport' % self.config.organization_id
        body = {
            'dateRange': {'startDateTime': start_datetime, 'endDateTime': end_datetime},
            'status': 2,
            'userIds': user_ids or [],
            'organizationUnitIds': [],
            'filterOrganizationUnitMembersHierarchically': False,
            'userGroupIds': [],
            'accessControlPointIds': [],
        }
        items = []
        skip = 0
        while True:
            page_body = dict(body, pagination={'skip': skip, 'take': take})
            page = self._authed_call('POST', path, page_body)
            page_items = page.get('items') or []
            items.extend(page_items)
            pagination = page.get('pagination') or {}
            total = pagination.get('total', len(items))
            _logger.info(
                'Armon API get_first_and_last_access_logs: skip=%s got=%s collected=%s/%s',
                skip, len(page_items), len(items), total)
            skip += take
            if not page_items or len(items) >= total:
                break
        return items
