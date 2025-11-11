# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment Super Power",
<<<<<<< 997ffaa65767da6f6a9e417b0af69f6fb47879a1
    "version": "19.0.1.0.0",
||||||| 83ab0e7521f93881476589b5c42674538c80ee20
    "version": "18.0.1.10.0",
=======
    "version": "18.0.1.11.0",
>>>>>>> 399b4ba4dd4d141383b7000cbff1ca7889d530da
    "category": "Payment",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "installable": True,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account",
        # TODO mover esto a modulo puente
        "l10n_latam_invoice_document",
        "account_internal_transfer",
        "l10n_latam_check",
    ],
    "data": [
        "security/payment_security.xml",
        "security/ir.model.access.csv",
        "wizards/account_payment_invoice_wizard_view.xml",
        "views/account_payment_view.xml",
        "views/account_move.xml",
        "views/account_write_off_type_views.xml",
        "views/res_company_setting.xml",
    ],
    "demo": [],
}
