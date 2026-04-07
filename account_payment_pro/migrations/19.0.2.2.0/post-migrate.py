"""
Post-migration script for account_payment_pro 19.0.2.2.0
=========================================================

Qué supone:
  - El módulo ya fue actualizado a 19.0.2.2.0.

Qué garantiza al terminar:
  - Para pagos con cotización forzada (force_amount_company_currency) y B1=C:
    counterpart_rate y counterpart_currency_amount reflejan la cotización real.
  - Para pagos con ambos counterpart_exchange_rate + force (combinación rota):
    B1=A, counterpart_rate=1.0, counterpart_currency_amount=amount.
  - counterpart_currency_amount es siempre positivo.
  - unreconciled_amount tiene signo correcto para escenarios migrados.

Contexto:
  El script 19.0.2.0.0 no corregía counterpart_rate para pagos con
  force_amount_company_currency (diarios en moneda extranjera con cotización
  forzada), lo que dejaba counterpart_currency_amount con valor incorrecto.
  Bases que ya corrieron el 19.0.2.0.0 necesitan estas correcciones.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ── 1. Pagos con ambos counterpart_exchange_rate + force (escenario b) ────
    # Combinación rota en el código viejo (condiciones mutuamente excluyentes).
    # counterpart_exchange_rate no tenía efecto real.
    # Fix: B1 = A (sin conversión de contrapartida), counterpart_rate = 1.0.
    has_both = openupgrade.column_exists(
        cr, "account_payment", "x_bkp_counterpart_exchange_rate"
    ) and openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency")
    if has_both:
        cr.execute("""
            UPDATE account_payment
            SET counterpart_currency_id = currency_id,
                counterpart_rate = 1.0,
                counterpart_currency_amount = amount
            WHERE x_bkp_counterpart_exchange_rate IS NOT NULL
              AND x_bkp_counterpart_exchange_rate != 0
              AND x_bkp_force_amount_company_currency IS NOT NULL
              AND x_bkp_force_amount_company_currency != 0
              AND counterpart_currency_id != currency_id;
        """)
        _logger.info(
            "account_payment_pro: fixed broken dual-rate payments (%s rows)",
            cr.rowcount,
        )

    # ── 2. Corregir counterpart_rate para B1=C con cotización forzada ─────────
    # Cuando B1 = company_currency y se forzó cotización, counterpart_rate
    # debe ser 1/accounting_rate. El 19.0.2.0.0 original no hacía esto.
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency"):
        cr.execute("""
            UPDATE account_payment ap
            SET counterpart_rate = 1.0 / ap.accounting_rate
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.counterpart_currency_id = rc.currency_id
              AND ap.counterpart_currency_id != ap.currency_id
              AND ap.accounting_rate IS NOT NULL
              AND ap.accounting_rate != 0
              AND ap.x_bkp_force_amount_company_currency IS NOT NULL
              AND ap.x_bkp_force_amount_company_currency != 0;
        """)
        _logger.info(
            "account_payment_pro: fixed counterpart_rate for B1=C forced payments (%s rows)",
            cr.rowcount,
        )

    # ── 3. Recalcular counterpart_currency_amount para registros con force ────
    # Tras corregir counterpart_rate, recalcular counterpart_currency_amount.
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency"):
        cr.execute("""
            UPDATE account_payment
            SET counterpart_currency_amount = CASE
                WHEN counterpart_currency_id IS NOT NULL
                     AND counterpart_currency_id != currency_id
                     AND counterpart_rate IS NOT NULL
                     AND counterpart_rate != 0
                THEN amount * counterpart_rate
                ELSE amount
            END
            WHERE x_bkp_force_amount_company_currency IS NOT NULL
              AND x_bkp_force_amount_company_currency != 0;
        """)
        _logger.info(
            "account_payment_pro: recalculated counterpart_currency_amount for forced payments (%s rows)",
            cr.rowcount,
        )

    # ── 4. Corregir write_off_amount para B1=C con force ─────────────────────
    # El 19.0.2.0.0 original usó counterpart_rate incorrecto para la conversión.
    # Si B1=C y force existía: counterpart_rate * accounting_rate debería ser 1.0
    # (write_off no cambia de moneda). Restauramos desde backup.
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_write_off_amount") and openupgrade.column_exists(
        cr, "account_payment", "x_bkp_force_amount_company_currency"
    ):
        cr.execute("""
            UPDATE account_payment ap
            SET write_off_amount = x_bkp_write_off_amount
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.counterpart_currency_id = rc.currency_id
              AND ap.counterpart_currency_id != ap.currency_id
              AND ap.x_bkp_write_off_amount IS NOT NULL
              AND ap.x_bkp_write_off_amount != 0
              AND ap.x_bkp_force_amount_company_currency IS NOT NULL
              AND ap.x_bkp_force_amount_company_currency != 0;
        """)
        _logger.info(
            "account_payment_pro: restored write_off_amount for B1=C forced payments (%s rows)",
            cr.rowcount,
        )

    # ── 5. counterpart_currency_amount: debe ser siempre positivo ─────────────
    cr.execute("""
        UPDATE account_payment
        SET counterpart_currency_amount = ABS(counterpart_currency_amount)
        WHERE counterpart_currency_amount < 0;
    """)
    _logger.info(
        "account_payment_pro: fixed counterpart_currency_amount sign (%s rows)",
        cr.rowcount,
    )

    # ── 6. unreconciled_amount: corregir signo para escenarios migrados ───────
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_write_off_amount"):
        cr.execute("""
            UPDATE account_payment
            SET unreconciled_amount = -unreconciled_amount
            WHERE unreconciled_amount != 0
              AND x_bkp_write_off_amount IS NOT NULL
              AND (
                  (partner_type = 'customer' AND payment_type = 'outbound')
                  OR (partner_type = 'supplier' AND payment_type = 'inbound')
              );
        """)
        _logger.info(
            "account_payment_pro: fixed unreconciled_amount sign for migrated payments (%s rows)",
            cr.rowcount,
        )
    else:
        _logger.info("account_payment_pro: backup column not found, skipping unreconciled_amount sign fix")
