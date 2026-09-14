# -*- coding: utf-8 -*-
"""Resolves the language/direction (LTR vs RTL) that drives export rendering.

Single decision point shared by both the xlsx writers and the PDF renderer,
so RTL logic is not duplicated between the two output formats.
"""


class DirectionResolver:
    """Decides which res.lang (and therefore direction) an export should use."""

    @staticmethod
    def _direction_for_lang(env, lang_code):
        if not lang_code:
            return 'ltr'
        data = env['res.lang']._get_data(code=lang_code)
        return data.direction if data else 'ltr'

    @classmethod
    def for_partner_report(cls, env, partner_id):
        """Per-partner reports (statement, aged balance): the partner's own lang."""
        lang = None
        if partner_id:
            partner = env['res.partner'].sudo().browse(partner_id)
            lang = partner.lang if partner.exists() else None
        lang = lang or env.user.lang
        return lang, cls._direction_for_lang(env, lang)

    @classmethod
    def for_summary_report(cls, env):
        """Multi-partner summary reports: the current logged-in user's lang."""
        lang = env.user.lang
        return lang, cls._direction_for_lang(env, lang)
