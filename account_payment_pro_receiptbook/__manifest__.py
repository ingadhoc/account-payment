# © 2024 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment receiptbook",
<<<<<<< HEAD
    "version": "18.0.1.2.0",
||||||| parent of da0d1971 (temp)
    "version": "17.0.1.5.0",
=======
    "version": "17.0.1.6.0",
>>>>>>> da0d1971 (temp)
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
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/account_payment_receipt_group.xml',
        'views/account_payment.xml',
        'data/l10n_latam.document.type.csv',
    ],
    'installable': True,
<<<<<<< HEAD
    'auto_install': ["account_payment_pro"],
||||||| parent of da0d1971 (temp)
    'auto_install': ["account_payment_pro","l10n_ar_account_tax_settlement"],
=======
    'auto_install': False,
>>>>>>> da0d1971 (temp)
    'application': False,
    'post_init_hook': '_generate_receiptbooks',
    "demo": [
    ],
}
