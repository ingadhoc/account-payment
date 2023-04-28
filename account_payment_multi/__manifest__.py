{
    'name': "Account payment multi",
    'description': """
        Allows payment multiple invoices with a single payment link
    """,
    'author': 'ADHOC SA',
    'website': "https://www.adhoc.com.ar",
    'category': 'Technical',
    'version': "15.0.1.0.0",
    'depends': ['account_payment'],
    'license': 'LGPL-3',
    'images': [
    ],
    'installable': True,
    'assets': {
        'web.assets_frontend': [
            'account_payment_multi/static/src/js/payment_form.js',
            'account_payment_multi/static/src/js/payment_multi.js',
        ],
    },    
    'data': [
        'views/payment_templates.xml',
        'views/account_portal_templates.xml',
        'wizards/payment_link_wizard_views.xml',
    ],
    'demo': [
    ],
}
