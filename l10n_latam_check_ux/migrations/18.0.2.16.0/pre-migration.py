"""Move the per-partner ``add_check_credit`` flag to the global setting.

The flag stops being a partner field: checks on hand are now added to the credit limit warning
for every partner when the database-wide setting is on. Turn the setting on if any partner had
the flag, so databases that were using it keep the behaviour. It runs before the update, while
the column still exists.
"""

import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not column_exists(cr, "res_partner", "add_check_credit"):
        return
    cr.execute("SELECT count(*) FROM res_partner WHERE add_check_credit")
    count = cr.fetchone()[0]
    if not count:
        return
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
        VALUES ('l10n_latam_check_ux.add_check_credit', 'True', 1, now() at time zone 'UTC', 1, now() at time zone 'UTC')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """
    )
    _logger.info("Check credit: %s partner(s) had it, global setting turned on", count)
