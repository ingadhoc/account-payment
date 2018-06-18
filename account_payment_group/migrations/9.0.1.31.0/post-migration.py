# -*- coding: utf-8 -*-
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(cr, version):
    openupgrade.load_data(
        cr, 'account_payment_group', 'migrations/9.0.1.31.0/mig_data.xml')
