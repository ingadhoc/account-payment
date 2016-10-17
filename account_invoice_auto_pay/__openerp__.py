# -*- coding: utf-8 -*-
{
    'author': 'ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'category': 'Accounting & Finance',
    'data': [
        'account_invoice_view.xml',
        'account_invoice_workflow.xml',
    ],
    'demo': [],
    'depends': [
        'account_voucher',
        'account_cancel',
    ],
    'description': '''
Account Invoice Auto Pay
========================
Auto pay invoice if residual = 0
''',
    'installable': False,
    'name': 'Account Invoice Auto Pay',
    'test': [],
    'version': '9.0.1.0.0',
}
