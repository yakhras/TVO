# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': "Stock Valuation per Warehouse",
    'summary': "Keep a separate product cost per warehouse, with cost history, "
               "landed costs and revaluation applied per warehouse.",
    'author': "Yaser Akhras",
    'maintainers': ["yakhras"],
    'website': "https://yaserakhras.com",
    'category': "Inventory/Inventory",
    'version': '18.0.1.0.1',
    'application': False,
    'license': 'AGPL-3',
    'depends': ['stock_landed_costs'],
    'data': [
        'security/ir.model.access.csv',
        "views/product_product_view.xml",
        "wizard/stock_valuation_layer_revaluation_views.xml",
    ],
}
