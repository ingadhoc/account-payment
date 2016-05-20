# -*- coding: utf-8 -*-
{'active': False,
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
It also addts dummy_journal_id and dummy_amount fields that can be used with
new api onchange events.
''',
    'installable': True,
    'name': 'Account Voucher Payline',
    'test': [],
    'version': '8.0.1.4.0',
 }
