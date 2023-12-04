# © 2023 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment invoice token",
    "version": "16.0.2.0.0",
    "category": "Accounting",
    "description": """This module allows you to associate an invoice with a payment token and make the electronic payment of the invoice.
                      - add a filter Electronic payment pending
                      - add a payment status "Electronic payment pending" for invoices that are associated to a payment
                           but are in pending or those that have a payment in done but have not yet been reconciled.""",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA",
    "license": "AGPL-3",
    "sequence": 100,
    "application": False,
    'installable': False,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_payment",
    ],
    "data": [
        'views/account_move.xml'
    ],
    "demo": [
    ],
}
