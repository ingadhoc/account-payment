# -*- coding: utf-8 -*-
{'active': False,
    'author': 'Ingenieria ADHOC',
    'website': 'www.ingadhoc.com',
    'license': 'AGPL-3',
    'category': 'Accounting & Finance',
    'data': [
        'workflow/account_voucher_workflow.xml',
        'views/account_voucher_view.xml',
        'views/res_company_view.xml',
        'views/account_journal_view.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [],
    'depends': [
        'account_voucher_withholding',
        'account_check',
    ],
    'description': '''
Account Voucher Double Validation
=================================
Add a new state called confirm on vouchers.
It also adds a payment date. Payments can not be validated before this payment
date.
''',
    'installable': True,
    'name': "Account Voucher Double Validation",
    'test': [],
    'version': '8.0.1.11.0'}
