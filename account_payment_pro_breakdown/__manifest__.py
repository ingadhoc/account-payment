##############################################################################
#
#    Copyright (C) 2026  ADHOC SA  (http://www.adhoc.com.ar)
#    All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    "name": "Account Payment Pro Breakdown",
    "version": "20.0.1.0.0",
    "category": "Accounting",
    "author": "ADHOC SA",
    "website": "https://www.adhoc.com.ar",
    "license": "AGPL-3",
    "summary": "Break down a payment between the selected debts, with an amount for each one",
    "depends": ["account_payment_pro"],
    "data": [
        "security/ir.access.csv",
        "views/account_payment_views.xml",
        "wizards/account_payment_breakdown_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
