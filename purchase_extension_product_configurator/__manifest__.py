{
    'name': "Purchase Extension Product Configurator",
    'summary': "Product configurator for Purchase Requisition lines.",
    'version': '18.0.1.0',
    'author': "Yaser Akhras",
    'website': "https://www.yaserakhras.com ",
    'license': 'AGPL-3',
    'application': False,

    'depends': ['purchase_requisition', 'sale', 'sale_extension', 'product'],

    'data': [
        'views/purchase_requisition_view.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'purchase_extension_product_configurator/static/src/js/**/*',
            'purchase_extension_product_configurator/static/src/xml/**/*',
        ],
    },
}
