{
    "name": "Payment Groups with Financial Surchange",
    "version": "13.0.1.0.0",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "category": "Payment",
    "depends": [
        "account_payment_group",
    ],
    "data": [
        'views/account_financing_plan_view.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
        'views/account_payment_group_views.xml',
        'views/account_move_views.xml',
        'wizards/res_config_settings_views.xml',
        'security/ir.model.access.csv',
    ],
    "demo": [
    ],
    'images': [
    ],
    'installable': True,
    'auto_install': False,
}
