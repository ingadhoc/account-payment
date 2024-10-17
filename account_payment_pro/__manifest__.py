# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment Super Power",
    "version": "17.0.2.0.0",
    "category": "Payment",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    'installable': True,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account",
        # TODO mover esto a modulo puente
        "l10n_latam_invoice_document",
    ],
    "data": [
        'security/payment_security.xml',
        'security/ir.model.access.csv',
        'wizards/account_payment_invoice_wizard_view.xml',
        'views/account_payment_view.xml',
        'views/account_move.xml',
        'views/account_write_off_type_views.xml',
        'views/res_company_setting.xml',
    ],
    "demo": [
    ],
}
