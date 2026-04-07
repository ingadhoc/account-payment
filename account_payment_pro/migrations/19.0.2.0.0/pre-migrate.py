"""
Pre-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Qué supone:
  - Existe la tabla account_payment con las columnas del modelo anterior.

Qué garantiza al terminar:
  - Las columnas que se eliminan o transforman tienen backup con prefijo x_bkp_.
  - Los datos originales quedan preservados para que el post-migrate los use.
  - No se hacen transformaciones aquí; todo lo hace el post-migrate para
    permitir re-ejecución en caso de bugfixes sin perder datos originales.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Backup de todas las columnas que se eliminan o transforman.
    # Los valores originales quedan en x_bkp_* para que el post-migrate
    # realice las transformaciones. Esto permite re-ejecutar el post
    # en caso de bugs sin perder datos originales.
    columns_to_backup = []
    for col in (
        "counterpart_exchange_rate",  # stored → backup real
        "force_amount_company_currency",  # stored → backup real
        "write_off_amount",  # stored → backup real
        # amount_company_currency y counterpart_currency_amount eran compute
        # sin store=True → no tienen columna en DB, no se backupean.
    ):
        if openupgrade.column_exists(cr, "account_payment", col):
            columns_to_backup.append((col, f"x_bkp_{col}", None))

    if columns_to_backup:
        openupgrade.copy_columns(cr, {"account_payment": columns_to_backup})
        _logger.info(
            "account_payment_pro: backed up columns: %s",
            [c[0] for c in columns_to_backup],
        )
