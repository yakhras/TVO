# -*- coding: utf-8 -*-

import logging

import requests
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class JotformClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def create_submission(self, form_id, answers):
        """POST a new submission. `answers` is already in the API's
        submission[qid] / submission[qid_subfield] param form. Returns the
        new submission's ID."""
        _logger.info(
            'Jotform API request: POST /form/%s/submissions fields=%s',
            form_id, sorted(answers.keys()))
        try:
            resp = requests.post(
                'https://api.jotform.com/form/%s/submissions' % form_id,
                params={'apiKey': self.api_key}, data=answers, timeout=15)
        except requests.exceptions.Timeout:
            _logger.warning('Jotform API request timed out: form %s', form_id)
            raise UserError('Jotform API request timed out.')
        except requests.exceptions.ConnectionError:
            _logger.warning('Jotform API connection error: form %s', form_id)
            raise UserError('Could not connect to Jotform API.')
        if resp.status_code != 200:
            _logger.warning(
                'Jotform API response: form %s -> %s: %s', form_id, resp.status_code, resp.text[:500])
            raise UserError('Jotform API error %s: %s' % (resp.status_code, resp.text[:300]))
        data = resp.json()
        submission_id = (data.get('content') or {}).get('submissionID')
        if not submission_id:
            _logger.warning('Jotform API response missing submissionID: %s', resp.text[:500])
            raise UserError('Jotform API did not return a submission ID.')
        _logger.info('Jotform API response: 200, submissionID=%s', submission_id)
        return submission_id
