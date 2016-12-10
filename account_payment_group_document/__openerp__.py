# -*- coding: utf-8 -*-
{
    "name": "Payment Groups with Accounting Documents",
    "version": "9.0.1.0.0",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "category": "Accounting",
    "depends": [
        "account_document",
        "account_payment_group",
    ],
    "data": [
        'view/account_payment_group_view.xml',
        'view/account_payment_view.xml',
        'wizards/account_payment_group_invoice_wizard_view.xml',
    ],
    "demo": [
    ],
    'images': [
    ],
    'installable': True,
    'auto_install': True,
}
