# -*- coding: utf-8 -*-
"""Shared QWeb-to-PDF rendering helper for balance export reports.

Our exports run over ad-hoc domains/params supplied by the frontend, not a
fixed recordset of res_ids, so we render through ir.actions.report's lower
level building blocks instead of the res_ids-bound _render_qweb_pdf.
"""


def render_balance_pdf(env, report_xmlid, template_xmlid, values):
    """Render `template_xmlid` with `values` and convert it to PDF bytes.

    `report_xmlid` supplies the ir.actions.report used for paperformat/
    header-footer resolution during PDF generation. `_render_template` (rather
    than a bare ir.qweb._render) is what injects the standard report globals
    (time, user, res_company, web_base_url) that web.external_layout expects.

    QWeb's _prepare_environment unconditionally sets its own `lang` render
    variable from self.env.context['lang'] (clobbering any 'lang' key passed
    via `values`), so the report direction/translation language must be
    driven through with_context, not through the values dict.
    """
    report_sudo = env.ref(report_xmlid).sudo().with_context(lang=values.get('lang'))
    html = report_sudo._render_template(template_xmlid, values)
    bodies, html_ids, header, footer, specific_paperformat_args = report_sudo._prepare_html(html)
    return report_sudo._run_wkhtmltopdf(
        bodies,
        report_ref=report_xmlid,
        header=header,
        footer=footer,
        specific_paperformat_args=specific_paperformat_args,
    )
