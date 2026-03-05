{
    "name": "Account Cashbox Bundle",
    "version": "18.0.1.1.0",
    "category": "Accounting",
    "summary": "Technical bridge module for account_cashbox and l10n_ar_payment_bundle",
    "author": "ADHOC SA",
    "website": "www.adhoc.com.ar",
    "license": "AGPL-3",
    "depends": [
        "account_cashbox",
        "l10n_ar_payment_bundle",
    ],
    "data": ["views/account_payment.xml"],
    "demo": ["demo/account_cashbox_bundle_demo.xml"],
    "installable": True,
    "auto_install": True,
}
