{
    'name': 'Custom RMA',
    'version': '1.0',
    'summary': 'Custom Return Merchandise Authorization Module',
    'category': 'Sales',
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'depends': ['base', 'sale', 'account', 'stock', 'mail', 'web_map'],
    'data': [
        'security/ir.model.access.csv',
        'data/rma_stage_data.xml',
        'report/rma_report_template.xml',
        'views/rma_views.xml',
        'views/rma_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}