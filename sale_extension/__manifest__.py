{
    'name': 'Sale Extension',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Sales feature toggles',
    'author': 'Yaser Akhras',
    'website': 'https://www.yaserakhras.com',
    'license': 'LGPL-3',
    'depends': ['sale'],
    'data': ['views/res_config_settings.xml'],
    'assets': {
        'web.assets_backend': [
            'sale_extension/static/src/js/sale_order_line_reference_match.js',
        ],
    },
    'installable': True,
}