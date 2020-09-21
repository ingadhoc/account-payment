# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
_logger = logging.getLogger(__name__)

def create_column_table(cr):
    cr.execute("""ALTER TABLE account_checkbook ADD COLUMN issue_check_subtype character varying""")
    cr.execute("""UPDATE account_checkbook SET issue_check_subtype=check_subtype""")
    # cr.execute("""ALTER TABLE account_checkbook DROP COLUMN check_subtype""")


def migrate(cr, version):
    create_column_table(cr)
