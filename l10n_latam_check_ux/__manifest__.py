##############################################################################
#
#    Copyright (C) 2015  ADHOC SA  (http://www.adhoc.com.ar)
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
    "name": "Latam Check UX",
    "version": "18.0.2.1.0",
    "category": "Accounting",
    "sequence": 14,
    "summary": "",
    "author": "ADHOC SA",
    "website": "www.adhoc.com.ar",
    "license": "AGPL-3",
    "images": [],
    "depends": [
        "l10n_latam_check",
        "account_ux",
        "account_internal_transfer",
    ],
    "data": [
        "wizards/account_check_action_wizard_view.xml",
        "views/account_payment_view.xml",
        "views/l10n_latam_check_view.xml",
        "views/account_journal_view.xml",
        "views/report_payment_receipt_templates.xml",
        "wizards/l10n_latam_payment_mass_transfer.xml",
        "reports/report_account_transfer.xml",
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "installable": True,
    "auto_install": True,
    "application": False,
}
