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
        "counterpart_exchange_rate",
        "force_amount_company_currency",
        "amount_company_currency",
        "write_off_amount",
        "counterpart_currency_amount",
    ):
        if openupgrade.column_exists(cr, "account_payment", col):
            columns_to_backup.append((col, f"x_bkp_{col}", None))

    if columns_to_backup:
        openupgrade.copy_columns(cr, {"account_payment": columns_to_backup})
        _logger.info(
            "account_payment_pro: backed up columns: %s",
            [c[0] for c in columns_to_backup],
        )

    # Pre-crear columnas de campos stored compute nuevos para que Odoo
    # NO dispare "Prepare computation" (recomputación masiva innecesaria).
    # El post-migrate las llenará con los valores correctos desde x_bkp_*.
    for col, col_type in [
        ("counterpart_rate", "DOUBLE PRECISION"),
        ("accounting_rate", "DOUBLE PRECISION"),
    ]:
        if not openupgrade.column_exists(cr, "account_payment", col):
            cr.execute(  # pylint: disable=sql-injection
                "ALTER TABLE account_payment ADD COLUMN %s %s" % (col, col_type)
            )
            _logger.info("account_payment_pro: pre-created column %s", col)
