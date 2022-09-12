{
    "name": "Payment Groups with Financial Surchange",
    "version": "15.0.1.0.1",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "category": "Payment",
    "depends": [
        "account_payment_group",
        "card_installment",
    ],
    "data": [
        'views/card_installment_view.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
        'views/account_payment_group_views.xml',
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
