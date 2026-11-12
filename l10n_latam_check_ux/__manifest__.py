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
<<<<<<< 4592e5f81cc82a8ed38362a4c9b042215da56f49
    "version": "19.0.2.5.0",
||||||| 8f5864c94fed37498cd37b133a89b0bbe35fb6c7
    "version": "18.0.2.15.0",
=======
    "version": "18.0.2.16.0",
>>>>>>> d2eeac124ec2ce5d368b12af2e9ef48d10664cdc
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
        "wizards/checks_to_date_view.xml",
        "wizards/account_check_reject_wizard_view.xml",
        "views/account_payment_view.xml",
        "views/l10n_latam_check_view.xml",
        "views/account_journal_view.xml",
        "views/report_payment_receipt_templates.xml",
        "views/res_config_settings_view.xml",
        "wizards/l10n_latam_payment_mass_transfer.xml",
        "reports/report_account_transfer.xml",
        "reports/report_checks_to_date.xml",
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "installable": True,
    "auto_install": True,
    "application": False,
}
