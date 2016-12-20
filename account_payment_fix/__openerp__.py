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
Several modification, fixes or improovements to payments:
* Fix domains for payment method, journal and partner on payment view so that is
not loosed when you enter an already created payment.
* It also fix available payment methods when you change several times the journal
* It also restrict destination journal selection if available inbound methods
* We also recreate the menu "Bank and Cash"
* Allow to make payments of child companies
''',
    'installable': True,
    'name': 'Account Payment Fix',
    'test': [],
    'version': '9.0.1.0.0',
}
