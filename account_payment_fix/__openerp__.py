# -*- coding: utf-8 -*-
{
    'author': 'ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'category': 'Accounting & Finance',
    'data': [
        'views/account_payment_view.xml',
    ],
    'demo': [],
    'depends': [
        'account'
    ],
    'description': '''
Account Payment Fix
===================
Fix domains for payment method and partner on payment view so that is not
loosed when you enter an already created payment.
It also fix available payment methods when you change several times the journal
''',
    'installable': True,
    'name': 'Account Payment Fix',
    'test': [],
    'version': '9.0.1.0.0',
}
