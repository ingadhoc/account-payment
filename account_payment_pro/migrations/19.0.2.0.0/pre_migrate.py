"""
Pre-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Qué supone:
  - Existe la tabla account_payment con las columnas del modelo anterior.
  - counterpart_exchange_rate es stored en formato user-friendly (ej: 1500 para USD→ARS).
  - amount_company_currency y amount están presentes y pobladas.
  - write_off_amount está en company_currency_id.

Qué garantiza al terminar:
  - La columna counterpart_rate existe con valores en formato Odoo nativo (ej: 0.000667).
  - La columna accounting_rate existe y está poblada para todos los registros.
  - Las columnas deprecated tienen backup con prefijo x_bkp_.
  - write_off_amount está expresado en destination_currency (usando counterpart_rate).
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ── 1. Backup de todas las columnas modificadas (antes de cualquier transformación) ──
    # Se capturan los valores originales con prefijo x_bkp_ para auditoría y rollback.
    # No se borran aquí; los drops los gestiona el ORM al instalar el módulo.
    columns_to_backup = []
    for col in (
        "counterpart_exchange_rate",
        "force_amount_company_currency",
        "amount_company_currency",
        "write_off_amount",
    ):
        if openupgrade.column_exists(cr, "account_payment", col):
            columns_to_backup.append((col, f"x_bkp_{col}", None))

    if columns_to_backup:
        openupgrade.copy_columns(cr, {"account_payment": columns_to_backup})
        _logger.info(
            "account_payment_pro: backed up columns: %s",
            [c[0] for c in columns_to_backup],
        )

    # ── 2. counterpart_exchange_rate → counterpart_rate ────────────────────────
    # El valor almacenado era user-friendly (ej: 1500 para "1 USD = 1500 ARS").
    # El nuevo campo usa formato Odoo nativo (A/C), ej: 0.000667 para ARS/USD.
    # Solo renombramos si la columna original todavía existe (idempotencia).
    if openupgrade.column_exists(cr, "account_payment", "counterpart_exchange_rate"):
        openupgrade.rename_columns(
            cr,
            {"account_payment": [("counterpart_exchange_rate", "counterpart_rate")]},
        )
        _logger.info("account_payment_pro: renamed counterpart_exchange_rate → counterpart_rate")

    cr.execute("""
        UPDATE account_payment
        SET counterpart_rate = 1.0 / counterpart_rate
        WHERE counterpart_rate IS NOT NULL
          AND counterpart_rate != 0;
    """)
    _logger.info(
        "account_payment_pro: inverted counterpart_rate values (%s rows updated)",
        cr.rowcount,
    )

    # ── 3. accounting_rate: nueva columna, poblar desde amount y amount_company_currency ──
    # exchange_rate era non-stored, no hay columna que renombrar.
    # accounting_rate = A/C en formato Odoo nativo = amount_company_currency / amount
    # (que era exactamente el inverso de exchange_rate user-friendly).
    cr.execute("""
        ALTER TABLE account_payment
        ADD COLUMN IF NOT EXISTS accounting_rate NUMERIC;
    """)
    cr.execute("""
        UPDATE account_payment
        SET accounting_rate = CASE
            WHEN amount IS NOT NULL AND amount != 0
                THEN amount_company_currency / amount
            ELSE 1.0
        END
        WHERE accounting_rate IS NULL;
    """)
    _logger.info(
        "account_payment_pro: populated accounting_rate (%s rows updated)",
        cr.rowcount,
    )

    # ── 4. write_off_amount: migrar de company_currency a destination_currency ──
    # El write_off_amount estaba en CLP/ARS/company_currency.
    # Hay que convertirlo a la moneda de contrapartida (destination_currency ≈ counterpart_currency).
    # Conversión: write_off_amount_new = write_off_amount_old / counterpart_rate (formato nativo)
    # Solo aplica cuando hay tasa y es distinta de 1 (pagos multicurrency).
    cr.execute("""
        UPDATE account_payment
        SET write_off_amount = write_off_amount / counterpart_rate
        WHERE write_off_amount IS NOT NULL
          AND write_off_amount != 0
          AND counterpart_rate IS NOT NULL
          AND counterpart_rate != 0
          AND counterpart_rate != 1.0;
    """)
    _logger.info(
        "account_payment_pro: migrated write_off_amount to destination_currency (%s rows updated)",
        cr.rowcount,
    )
