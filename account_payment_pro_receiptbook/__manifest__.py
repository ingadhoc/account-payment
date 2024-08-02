# © 2024 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment receiptbook",
    "version": "17.0.1.2.0",
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
    'auto_install': False,
    'application': False,
    'post_init_hook': '_generate_receiptbooks',
    "demo": [
    ],
}
