# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Check Cashbox management",
    "summary": "Add cashbox for check operations",
    "version": "17.0.1.1.0",
    "category": "Accounting",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "depends": [
        "account_cashbox",
        "l10n_latam_check",
        ],
    "demo": [],
    "data": [
        'views/account_payment_view.xml',
        'wizards/l10n_latam_payment_mass_transfer_views.xml',
        ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
