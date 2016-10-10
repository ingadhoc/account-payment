# -*- coding: utf-8 -*-
{
    'author': 'ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'category': 'Accounting & Finance',
    'data': [
        'views/account_voucher_view.xml',
    ],
    'demo': [],
    'depends': [
        'account_voucher'
    ],
    'description': '''
Account Voucher Payline
=======================
Module that modifies account voucher so that you can extend this module and add
other payment lines that can generate new account.move.lines.
It is used, for example, in 'account_check' and 'account_voucher_withholding'.
''',
    'installable': False,
    'name': 'Account Voucher Payline',
    'test': [],
    'version': '9.0.1.0.0',
}
