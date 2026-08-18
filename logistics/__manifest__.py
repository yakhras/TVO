{
    'name': 'Logistics',
    'version': '18.0.1.0.0',
    'category': 'Logistics',
    'summary': 'Import operations tracking: containers, B/L, customs',
    'description': """
        Replaces the import tracking spreadsheet.
        Tracks: Import Deals, Bills of Lading, Containers, Container Lines,
        Customs Declarations, Ports.
    """,
    'depends': [
        'base',
        'mail',
        'purchase_requisition',
        'product',
        'account',
    ],
    'data': [
        'security/logistics_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/partner_categories.xml',
        'views/logistics_port_views.xml',
        'views/logistics_shipping_line_views.xml',
        'wizards/logistics_container_link_wizard_views.xml',
        'views/logistics_bill_lading_views.xml',
        'views/logistics_container_views.xml',
        'views/logistics_container_line_views.xml',
        'views/purchase_requisition_views.xml',
        'views/logistics_dashboard.xml',
        'views/logistics_declaration_type_views.xml',
        'views/actions_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'logistics/static/src/components/logistics_dashboard/logistics_dashboard.js',
            'logistics/static/src/components/logistics_dashboard/logistics_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
