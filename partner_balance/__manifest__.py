# -*- coding: utf-8 -*-
{
    'name': "partner_balance",

    'summary': """
        Partner Balance""",

    'description': """
        Partner Balance. 
    """,

    'author': "Yaser Akhras",
    'website': "https://www.yaserakhras.com",

    'version': '18.0.2.0.0',
    'application': True,
    'license': 'AGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account', 'sale'],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        "views/partner_balance_view.xml",
        'views/aged_balance_view.xml',
        'views/partner_balance_config_view.xml',
        'views/account_move_views.xml',
        'report/report_actions.xml',
        'report/report_templates.xml',

    ],

    'assets': {
        'web.assets_backend': [
            'partner_balance/static/src/scss/partner_balance.scss',
            'partner_balance/static/src/js/components/partner_balance_toolbar.js',
            'partner_balance/static/src/js/partner_balance_list_controller.js',
            'partner_balance/static/src/js/partner_balance_list_view.js',
            'partner_balance/static/src/js/ledger_balance_list_controller.js',
            'partner_balance/static/src/js/aged_balance_summary_list_controller.js',
            'partner_balance/static/src/xml/partner_balance_toolbar.xml',
            'partner_balance/static/src/xml/partner_balance_template.xml',
            'partner_balance/static/src/xml/ledger_balance_template.xml',
            'partner_balance/static/src/xml/aged_balance_summary_template.xml',
        ],
    },

    'post_init_hook': 'post_init_hook',
}
