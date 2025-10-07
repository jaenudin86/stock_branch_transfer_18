{
    'name': 'Stock Branch Transfer',
    'version': '1.1',
    'depends': ['stock'],
    'author': 'Jae',
    'category': 'Inventory',
    'summary': 'Internal transfer antar cabang dengan request/approve dan auto DO/Receipt',
    'description': 'Menambahkan alur request dan approve untuk transfer antar cabang/gudang. Otomatis membuat Delivery & Receipt saat approve.',
    'data': [
        'security/ir.model.access.csv',
        'views/stock_branch_transfer_views.xml',
    ],
    'installable': True,
    'application': False,
}
