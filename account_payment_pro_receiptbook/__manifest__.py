# © 2024 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment receiptbook",
    "version": "18.0.1.4.0",
    "category": "Payment",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_payment_pro",
        "l10n_latam_invoice_document",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/account_payment_receipt_group.xml",
        "views/account_payment.xml",
        "views/res_company_setting.xml",
        "views/account_journal_views.xml",
        "data/l10n_latam.document.type.csv",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "post_init_hook": "_generate_receiptbooks",
    "post_load": "monkey_patches",
    "uninstall_hook": "uninstall_hook",
    "demo": [],
}
