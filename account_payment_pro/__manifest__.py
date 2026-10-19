# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment Super Power",
<<<<<<< 1826d11a7fd511786b1cf8cf95e235a87c2d39fb
    "version": "19.0.3.2.0",
||||||| fc8c538024527752ff9690cc6f18d49ff6c2cd59
    "version": "18.0.1.15.0",
=======
    "version": "18.0.1.16.0",
>>>>>>> 490f965e127fb09845b6ab09d7e825b2b98a76ce
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
        "account_ux",
    ],
    "data": [
        "security/payment_security.xml",
        "security/ir.model.access.csv",
        "wizards/account_payment_invoice_wizard_view.xml",
        "wizards/mail_compose_message_view.xml",
        "data/ir_cron.xml",
        "views/account_payment_view.xml",
        "views/account_move.xml",
        "views/account_write_off_type_views.xml",
        "views/res_company_setting.xml",
        "views/report_payment_receipt_template.xml",
    ],
    "demo": [],
    "post_init_hook": "_post_init_hooks",
}
