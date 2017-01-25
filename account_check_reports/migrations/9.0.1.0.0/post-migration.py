# -*- coding: utf-8 -*-
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(cr, version):
    openupgrade.load_data(
        cr, 'account_check_reports', 'report/account_check_deposit_report.xml')
