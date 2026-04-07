"""
Post-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Se ejecuta después de que el ORM cargó el nuevo código del módulo.

Qué supone:
  - El pre-migrate creó columnas x_bkp_* con los valores originales.
  - El ORM ya creó/recomputó counterpart_rate, accounting_rate y
    counterpart_currency_amount con tasas de mercado actuales (INCORRECTAS
    para registros históricos).

Qué garantiza al terminar:
  - counterpart_rate contiene el rate histórico (1 / x_bkp_counterpart_exchange_rate).
  - accounting_rate contiene el rate efectivo (amount / x_bkp_amount_company_currency).
  - write_off_amount está convertido de company_currency a destination_currency.
  - counterpart_currency_amount refleja los valores originales.

Re-ejecutable: todas las transformaciones leen de x_bkp_* (inmutables),
por lo que corregir un bug y volver a correr el post es seguro.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ── 1. counterpart_rate: restaurar rate histórico ──────────────────────────
    # El valor original era user-friendly (ej: 1428.108 para "1 USD = 1428.108 ARS").
    # El nuevo campo usa formato Odoo nativo A→B1 (ej: 0.000700 = USD/ARS).
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_counterpart_exchange_rate"):
        cr.execute("""
            UPDATE account_payment
            SET counterpart_rate = 1.0 / x_bkp_counterpart_exchange_rate
            WHERE x_bkp_counterpart_exchange_rate IS NOT NULL
              AND x_bkp_counterpart_exchange_rate != 0;
        """)
        _logger.info(
            "account_payment_pro: restored counterpart_rate from backup (%s rows)",
            cr.rowcount,
        )

    # ── 2. accounting_rate: restaurar rate efectivo ────────────────────────────
    # amount_company_currency era compute sin store → no hay backup directo.
    # Cuando el usuario forzó la cotización se guardaba en force_amount_company_currency
    # (campo almacenado), del cual sí tenemos backup.
    # accounting_rate = A/C = amount / force_amount_company_currency.
    # Para pagos sin force, el ORM ya lo computa correctamente al cargar el módulo.
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency"):
        cr.execute("""
            UPDATE account_payment
            SET accounting_rate = amount / x_bkp_force_amount_company_currency
            WHERE x_bkp_force_amount_company_currency IS NOT NULL
              AND x_bkp_force_amount_company_currency != 0;
        """)
        _logger.info(
            "account_payment_pro: restored accounting_rate from force_amount_company_currency backup (%s rows)",
            cr.rowcount,
        )

    # ── 3. write_off_amount: convertir de company_currency (C) a destination_currency (B1) ──
    # Fórmula: write_off_new = write_off_old × counterpart_rate × accounting_rate
    #   counterpart_rate = B1/A, accounting_rate = A/C → producto = B1/C
    #   Cuando A == C (lo más común), accounting_rate = 1 y simplifica a × counterpart_rate.
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_write_off_amount"):
        cr.execute("""
            UPDATE account_payment
            SET write_off_amount = x_bkp_write_off_amount * counterpart_rate * accounting_rate
            WHERE x_bkp_write_off_amount IS NOT NULL
              AND x_bkp_write_off_amount != 0
              AND counterpart_rate IS NOT NULL
              AND counterpart_rate != 0
              AND accounting_rate IS NOT NULL
              AND accounting_rate != 0
              AND counterpart_rate * accounting_rate != 1.0;
        """)
        _logger.info(
            "account_payment_pro: migrated write_off_amount to destination_currency (%s rows)",
            cr.rowcount,
        )

    # ── 4. counterpart_currency_amount: pre-poblar para evitar recompute masivo ──
    # Era compute sin store=True en el código viejo → no hay backup.
    # En el nuevo código es store=True; si no lo poblamos aquí el ORM encola un
    # recompute para todos los registros históricos (ADR-009).
    # Fórmula idéntica a _compute_counterpart_currency_amount:
    #   A != B1 → amount × counterpart_rate  |  A == B1 → amount
    # counterpart_rate ya fue corregido en el paso 1, así que los valores son correctos.
    cr.execute("""
        UPDATE account_payment
        SET counterpart_currency_amount = CASE
            WHEN counterpart_currency_id IS NOT NULL
                 AND counterpart_currency_id != currency_id
                 AND counterpart_rate IS NOT NULL
                 AND counterpart_rate != 0
            THEN amount * counterpart_rate
            ELSE amount
        END;
    """)
    _logger.info(
        "account_payment_pro: pre-populated counterpart_currency_amount (%s rows)",
        cr.rowcount,
    )

    # ── 5. Validación ─────────────────────────────────────────────────────────
    cr.execute("""
        SELECT COUNT(*) FROM account_payment
        WHERE state != 'draft'
          AND (accounting_rate IS NULL OR counterpart_rate IS NULL);
    """)
    count = cr.fetchone()[0]
    if count:
        _logger.warning(
            "account_payment_pro migration: %d posted payments with NULL accounting_rate "
            "or counterpart_rate — review migration results.",
            count,
        )
    else:
        _logger.info(
            "account_payment_pro migration: all posted payments have accounting_rate " "and counterpart_rate populated."
        )
