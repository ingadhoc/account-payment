# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment invoice token",
    "version": "16.0.2.0.0",
    "category": "Accounting",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "sequence": 100,
    "application": False,
    "installable": False,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_payment",
    ],
    "data": ["views/account_move.xml"],
    "demo": [],
}
