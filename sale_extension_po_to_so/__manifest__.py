{
    'name': 'Sale Extension - PO to SO',
    'version': '18.0.1.0.0',
    'summary': 'Convert confirmed/locked Purchase Orders into a draft Sale Order',
    'description': """
        Adds a wizard, restricted to a dedicated user group, that lets a salesperson
        pick one or more confirmed and locked Purchase Orders and convert them into
        a single draft Sale Order. Products, quantities and prices can be carried
        over as-is, adjusted in bulk (fixed amount or percentage), or edited
        manually per line, before choosing the target customer, warehouse and
        pricelist.
    """,
    'category': 'Sales/Purchase',
    'author': 'Yaser Akhras',
    'website': 'https://www.yaserakhras.com',
    'license': 'LGPL-3',
    'depends': [
        'sale_stock',
        'purchase',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizards/po_to_so_wizard.xml',
        'views/sale_menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
