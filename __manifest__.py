{
    'name': 'Stock Branch Transfer (Odoo 18)',
    'version': '1.0.0',
    'author': 'Jay IT Consultant',
    'category': 'Inventory',
    'summary': 'Internal branch transfer / request flow (Request → Send → Receive) compatible with Odoo 18',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/sequence_data.xml',
        'views/stock_branch_transfer_request_view.xml',
        'views/stock_branch_transfer_delivery_view.xml',
        'views/stock_branch_transfer_receive_view.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
