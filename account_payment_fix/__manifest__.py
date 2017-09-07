# -*- coding: utf-8 -*-
{
    'author': 'ADHOC SA,Odoo Community Association (OCA)',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'category': 'Accounting & Finance',
    'data': [
        'views/account_payment_view.xml',
    ],
    'demo': [],
    'depends': [
        'account',
        # por el backport
        'account_cancel',
    ],
    'installable': True,
    'name': 'Account Payment Fix',
    'test': [],
    'version': '10.0.1.1.0',
}
