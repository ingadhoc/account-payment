{
    "name": "Payment Groups with Accounting Documents",
    "version": "9.0.1.2.0",
    "author": "ADHOC SA,Odoo Community Association (OCA)",
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
    'installable': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
}
