# © 2024 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Argentinean Payment bundle",
    "version": "18.0.1.2.0",
    "category": "Payment",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "countries": ["ar"],
    "icon": "/base/static/img/country_flags/ar.png",
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_payment_pro",
        "l10n_ar_tax",
        "account_payment_pro_receiptbook",
    ],
    "data": [
        "data/account_payment_method_data.xml",
        "views/account_payment_view.xml",
        "views/report_payment_receipt_templates.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "demo": [],
    "post_init_hook": "post_init_hook",
}
