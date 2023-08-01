# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment with Multiple methods",
    "version": "16.0.1.5.0",
    "category": "Accounting",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA, AITIC S.A.S",
    "license": "AGPL-3",
    "application": False,
    'installable': True,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_ux",
        "l10n_latam_account_sequence",
    ],
    "data": [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizards/account_payment_group_invoice_wizard_view.xml',
        'wizards/res_config_settings_views.xml',
        'views/menuitem.xml',
        'views/account_payment_receiptbook_view.xml',
        'views/account_payment_view.xml',
        'views/account_move_line_view.xml',
        'views/account_payment_group_view.xml',
        'views/account_journal_dashboard_view.xml',
        'views/report_payment_group.xml',
        'data/decimal_precision_data.xml',
        'data/l10n_latam.document.type.csv',
        'data/mail_template_data.xml',
        'data/account_payment_data.xml',
        'data/ir_actions_server_data.xml',
    ],
    "demo": [
    ],
    'post_init_hook': 'post_init_hook',
}
