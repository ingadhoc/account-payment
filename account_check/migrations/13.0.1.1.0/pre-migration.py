# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
_logger = logging.getLogger(__name__)

def create_column_table(cr):
    cr.execute("""ALTER TABLE account_checkbook ADD COLUMN check_subtype character varying""")
    cr.execute("""UPDATE account_checkbook SET check_subtype=issue_check_subtype""")


def migrate(cr, version):
    create_column_table(cr)
