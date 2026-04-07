"""
Pre-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Qué supone:
  - Existe la tabla account_payment con las columnas del modelo anterior.

Qué garantiza al terminar:
  - Las columnas originales tienen backup con prefijo x_bkp_.
  - Las nuevas columnas almacenadas (accounting_rate, counterpart_rate,
    counterpart_currency_amount) existen con defaults seguros para evitar
    que el ORM encole un recompute masivo al cargar el módulo nuevo.
  - No se hacen transformaciones de valores aquí; el post-migrate se
    encarga de toda la lógica de conversión.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ── 0. Sentinel de migración ──────────────────────────────────────────────
    # Marca todas las filas existentes como "migradas". El post-migrate filtra
    # cada UPDATE por esta columna para que pagos creados después de la
    # migración nunca sean tocados, incluso si el post se re-ejecuta.
    if not openupgrade.column_exists(cr, "account_payment", "x_bkp_migrated"):
        cr.execute("ALTER TABLE account_payment ADD COLUMN x_bkp_migrated BOOLEAN")
        cr.execute("UPDATE account_payment SET x_bkp_migrated = TRUE")
        _logger.info("account_payment_pro: marked %s rows as x_bkp_migrated", cr.rowcount)

    # ── 1. Backup de columnas originales ──────────────────────────────────────
    # Estos backups son inmutables: el post-migrate lee siempre de x_bkp_*
    # para ser re-ejecutable de forma segura.
    columns_to_backup = []
    for col in (
        "counterpart_exchange_rate",
        "force_amount_company_currency",
        "write_off_amount",
        "unreconciled_amount",
    ):
        if openupgrade.column_exists(cr, "account_payment", col):
            columns_to_backup.append((col, f"x_bkp_{col}", None))

    if columns_to_backup:
        openupgrade.copy_columns(cr, {"account_payment": columns_to_backup})
        _logger.info(
            "account_payment_pro: backed up columns: %s",
            [c[0] for c in columns_to_backup],
        )

    # ── 2. Renombrar counterpart_exchange_rate → counterpart_rate ─────────────
    # Evita que el ORM cree la columna como campo nuevo y encole recompute.
    # Los valores quedan en formato viejo; el post-migrate los transforma.
    if openupgrade.column_exists(cr, "account_payment", "counterpart_exchange_rate"):
        openupgrade.rename_columns(cr, {"account_payment": [("counterpart_exchange_rate", "counterpart_rate")]})
        _logger.info("account_payment_pro: renamed counterpart_exchange_rate → counterpart_rate")

    # ── 3. Pre-crear accounting_rate ──────────────────────────────────────────
    # Campo nuevo store=True. Crear la columna evita que el ORM la registre como
    # nueva y encole recompute masivo al cargar el módulo. Los valores los pone
    # el post-migrate.
    if not openupgrade.column_exists(cr, "account_payment", "accounting_rate"):
        cr.execute("ALTER TABLE account_payment ADD COLUMN accounting_rate float8")
        _logger.info("account_payment_pro: pre-created accounting_rate column")

    # ── 4. Pre-crear counterpart_currency_amount ──────────────────────────────
    # Era compute sin store=True → no existía columna. Ahora es store=True.
    # Crear la columna evita el recompute masivo. Los valores los pone el post.
    if not openupgrade.column_exists(cr, "account_payment", "counterpart_currency_amount"):
        cr.execute("ALTER TABLE account_payment ADD COLUMN counterpart_currency_amount numeric")
        _logger.info("account_payment_pro: pre-created counterpart_currency_amount column")
