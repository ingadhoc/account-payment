# © 2022 juanpgarza - Juan Pablo Garza <juanp@juanpgarza.com>
# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Point of payment",
    "summary": "Introduces concept of point of payment and accounting journal sessions",
    "version": "16.0.1.0.1",
    "category": "Accounting",
    "website": "www.adhoc.com.ar",
    "author": "juanpgarza, ADHOC SA",
    "license": "AGPL-3",
    "depends": [
        "account",
        ],
    "data": [
        #'data/point_of_payment_data.xml', -> demodata
        'security/pop_security.xml',
        'security/ir.model.access.csv',
        'views/pop_config_views.xml',
        'views/pop_session_views.xml',
        'views/res_users_views.xml',
        'views/account_payment.xml',
        #'views/templates.xml',
        'views/menus.xml',
        'wizards/pop_payment_import.xml',
        'wizards/account_payment_register.xml',
        ],
    "development_status": "Production/Stable",
    "installable": True,
    "application": True,
}
