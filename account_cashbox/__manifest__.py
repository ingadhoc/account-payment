# © 2022 juanpgarza - Juan Pablo Garza <juanp@juanpgarza.com>
# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Cashbox management",
    "summary": "Introduces concept cashbox and accounting journal sessions",
    "version": "17.0.1.2.0",
    "category": "Accounting",
    "website": "www.adhoc.com.ar",
    "author": "juanpgarza, ADHOC SA",
    "license": "AGPL-3",
    "depends": [
        "account_ux",
        # la dependencia con payment pro es solo para forzar utilizar el metodo parcheado
        # _compute_available_journal_ids
        ],
    "demo": [
        'demo/cashbox_demo.xml',
    ],
    "data": [
        'security/cashbox_security.xml',
        'security/ir.model.access.csv',
        'views/account_cashbox_session.xml',
        'views/account_cashbox.xml',
        'views/res_users_views.xml',
        'views/account_payment.xml',
        'views/menuitem.xml',
        'wizards/account_cashbox_payment_import.xml',
        'wizards/account_payment_register.xml',
        ],
    'installable': True,
    "application": False,
}
