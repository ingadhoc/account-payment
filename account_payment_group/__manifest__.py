# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment with Multiple methods",
    "version": "10.0.1.0.0",
    "category": "Accounting",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    'installable': True,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_cancel",
        "account_financial_amount",
        "account_payment_fix",  # for fixes related to domains on payments
        # "account",
    ],
    "data": [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizards/account_payment_group_invoice_wizard_view.xml',
        'wizards/res_config_view.xml',
        'views/account_payment_view.xml',
        'views/account_move_line_view.xml',
        'views/account_payment_group_view.xml',
        'views/account_invoice_view.xml',
        'views/account_journal_dashboard_view.xml',
        'views/res_config_view.xml',
        # "views/assets.xml",
        # "views/report_name.xml",
        # "views/res_partner_view.xml",
        # "wizard/wizard_model_view.xml",
    ],
    "demo": [
        # "demo/res_partner_demo.xml",
        'demo/ir_config_parameter_demo.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
