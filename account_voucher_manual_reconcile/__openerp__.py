# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Voucher Manual Reconcile",
    "summary": "Avoid automatic computation of voucher lines",
    "version": "8.0.1.0.0",
    "category": "Uncategorized",
    "website": "www.adhoc.com.ar",
    "author": "ADHOC SA, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "account_voucher",
    ],
    "data": [
        'views/account_voucher_view.xml',
    ],
    "demo": [
    ],
    "qweb": [
    ]
}
