import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):

    _logger.info("Setting inital values for withholdable_advanced_amount")
    env.cr.execute(
        """
    UPDATE account_payment_group
    SET withholdable_advanced_amount = unreconciled_amount"""
    )
