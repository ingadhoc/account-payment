{
    'name': 'Account Payment Multi',
    "version": "17.0.1.0.0",
    'summary': 'Manage multiple payments in Odoo',
    'description': 'This module allows to pay multiple invoices with a single payment',
    'author': 'Odoo, ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'category': 'Technical',
    'depends': ['account_payment'],
    'assets': {
        'web.assets_frontend': [
            'account_payment_multi/static/src/js/payment_form.js',
        ],
    },
    'data': [
        "views/account_portal_templates.xml",
        "views/payment_form_template.xml"
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
