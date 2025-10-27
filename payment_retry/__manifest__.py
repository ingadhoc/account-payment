{
    "name": "payment retry",
    "author": "ADHOC SA",
    "website": "https://www.adhoc.inc",
    "category": "Payment",
    "version": "19.0.1.0.0",
    "depends": ["account_payment"],
    "license": "LGPL-3",
    "images": [],
    "installable": True,
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "wizards/payment_transaction_retry.xml",
    ],
}
