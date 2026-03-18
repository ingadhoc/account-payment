"""
Post-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Se ejecuta después de que el ORM cargó el nuevo código del módulo.

Qué garantiza:
  - Emite warning si quedan pagos confirmados con accounting_rate o counterpart_rate en NULL,
    lo que indicaría un problema en el pre_migrate o datos inesperados.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT COUNT(*) FROM account_payment
        WHERE state != 'draft'
          AND (accounting_rate IS NULL OR counterpart_rate IS NULL);
    """)
    count = cr.fetchone()[0]
    if count:
        _logger.warning(
            "account_payment_pro migration: %d posted payments with NULL accounting_rate "
            "or counterpart_rate — review pre_migrate results.",
            count,
        )
    else:
        _logger.info(
            "account_payment_pro migration: all posted payments have accounting_rate " "and counterpart_rate populated."
        )
