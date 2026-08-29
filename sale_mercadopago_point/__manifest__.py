{
    "name": "Sale MercadoPago Point",
    "version": "18.0.1.0.0",
    "category": "Payment",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "auto_install": False,
    "external_dependencies": {
        "python": ["requests"],
        "bin": [],
    },
    "depends": [
        "account",
    ],
    "data": [
        "data/account_payment_method_data.xml",
        "views/account_journal_views.xml",
        "views/account_payment_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "demo": [],
}
