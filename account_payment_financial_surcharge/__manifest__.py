{
    "name": "Payments with Financial Surchange",
    "version": "17.0.1.2.0",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "category": "Payment",
    "depends": [
        "account_payment_pro",
        "card_installment",
    ],
    "data": [
        'views/card_installment_view.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
        'views/account_move_views.xml',
        'wizards/res_config_settings_views.xml',
    ],
    "demo": [
    ],
    'images': [
    ],
    'installable': True,
    'auto_install': False,
}
