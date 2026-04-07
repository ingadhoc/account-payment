"""
Post-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Se ejecuta después de que el ORM cargó el nuevo código del módulo.

Qué supone:
  - El pre-migrate creó columnas x_bkp_* con los valores originales.
  - counterpart_currency_id ya existía como campo almacenado; la columna
    conserva los valores pre-refactor (puede haber NULLs del viejo compute).
  - counterpart_rate fue renombrado desde counterpart_exchange_rate (pre-migrate).
  - accounting_rate y counterpart_currency_amount fueron pre-creados en pre-migrate.

Qué garantiza al terminar:
  - counterpart_rate contiene el rate histórico (1 / x_bkp_counterpart_exchange_rate).
  - accounting_rate contiene el rate efectivo (amount / x_bkp_force_amount_company_currency).
  - Pagos con ambos counterpart_exchange_rate + force: B1=A, counterpart_rate=1.0.
  - counterpart_currency_id poblado para todos los pagos (NULLs resueltos).
  - counterpart_rate para B1=C con cotización forzada: 1/accounting_rate.
  - write_off_amount convertido de company_currency a destination_currency.
  - counterpart_currency_amount pre-poblado y siempre positivo.
  - unreconciled_amount con signo correcto para escenarios migrados.

Re-ejecutable: las primeras transformaciones leen de x_bkp_* (inmutables),
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
            "account_payment_pro: [step 1] restored counterpart_rate from backup (%s rows)",
            cr.rowcount,
        )

    # ── 2. accounting_rate: restaurar rate efectivo ────────────────────────────
    # amount_company_currency era compute sin store → no hay backup directo.
    # Cuando el usuario forzó la cotización se guardaba en force_amount_company_currency
    # (campo almacenado), del cual sí tenemos backup.
    # accounting_rate = A/C = amount / force_amount_company_currency.
    # Solo cuando A ≠ C: si A = C, accounting_rate es siempre 1.0 y el force
    # era un artefacto de other_currency=True en transferencias internas.
    # Para pagos sin force, el pre-migrate ya lo pobló desde res_currency_rate.
    if openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency"):
        cr.execute("""
            UPDATE account_payment ap
            SET accounting_rate = ap.amount / ap.x_bkp_force_amount_company_currency
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.currency_id != rc.currency_id
              AND ap.x_bkp_force_amount_company_currency IS NOT NULL
              AND ap.x_bkp_force_amount_company_currency != 0;
        """)
        _logger.info(
            "account_payment_pro: [step 2] restored accounting_rate from force backup (%s rows)",
            cr.rowcount,
        )

    # ── 3. Escenario (b): pagos con AMBOS counterpart_exchange_rate Y force ──
    # En el código viejo _use_counterpart_currency() requería currency_id == company_currency_id,
    # mientras que force_amount_company_currency requería other_currency = True.
    # Condiciones mutuamente excluyentes → combinación rota, counterpart_exchange_rate
    # no tenía efecto real.
    # Fix: setear B1 = A (sin conversión de contrapartida), counterpart_rate = 1.0.
    # El accounting_rate del step 2 ya captura la cotización forzada A↔C.
    has_both = openupgrade.column_exists(
        cr, "account_payment", "x_bkp_counterpart_exchange_rate"
    ) and openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency")
    if has_both:
        cr.execute("""
            UPDATE account_payment
            SET counterpart_currency_id = currency_id,
                counterpart_rate = 1.0
            WHERE x_bkp_counterpart_exchange_rate IS NOT NULL
              AND x_bkp_counterpart_exchange_rate != 0
              AND x_bkp_force_amount_company_currency IS NOT NULL
              AND x_bkp_force_amount_company_currency != 0;
        """)
        _logger.info(
            "account_payment_pro: [step 3] fixed dual-rate payments (counterpart_exchange_rate + force) (%s rows)",
            cr.rowcount,
        )

    # ── 4. counterpart_currency_id: poblar NULLs ──────────────────────────────
    # counterpart_currency_id existía como store=True antes del refactor; la columna
    # conserva valores previos. El viejo compute seteaba False/NULL cuando
    # journal.currency == counterpart_currency. Aquí completamos todos los NULLs
    # siguiendo la lógica del nuevo compute, ANTES de los pasos que dependen de él.
    _populate_counterpart_currency_id(cr)

    # ── 5. counterpart_rate para B1=C cuando se forzó cotización ──────────────
    # Cuando B1 = company_currency (diario extranjero pagando deuda local),
    # counterpart_rate = B1/A = C/A = 1/accounting_rate.
    # El step 2 corrigió accounting_rate, pero counterpart_rate aún tiene el valor
    # pre-refactor. Lo actualizamos.
    # Depende de: counterpart_currency_id poblado (step 4).
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
            "account_payment_pro: [step 5] fixed counterpart_rate for B1=C forced payments (%s rows)",
            cr.rowcount,
        )

    # ── 6. write_off_amount: convertir de company_currency (C) a destination_currency (B1) ──
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
            "account_payment_pro: [step 6] migrated write_off_amount to destination_currency (%s rows)",
            cr.rowcount,
        )

    # ── 7. counterpart_currency_amount: poblar ────────────────────────────────
    # Era compute sin store=True en el código viejo → no hay backup.
    # En el nuevo código es store=True; si no lo poblamos el ORM encola un
    # recompute masivo (ADR-009).
    # Fórmula idéntica a _compute_counterpart_currency_amount:
    #   A != B1 → amount × counterpart_rate  |  A == B1 → amount
    # Depende de: counterpart_currency_id (step 4) y counterpart_rate (steps 1/3/5).
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
        "account_payment_pro: [step 7] pre-populated counterpart_currency_amount (%s rows)",
        cr.rowcount,
    )

    # ── 8. counterpart_currency_amount: debe ser siempre positivo ─────────────
    cr.execute("""
        UPDATE account_payment
        SET counterpart_currency_amount = ABS(counterpart_currency_amount)
        WHERE counterpart_currency_amount < 0;
    """)
    _logger.info(
        "account_payment_pro: [step 8] fixed counterpart_currency_amount sign (%s rows)",
        cr.rowcount,
    )

    # ── 9. unreconciled_amount: corregir signo para escenarios migrados ───────
    # El refactor cambió el currency_field de unreconciled_amount, lo que invierte
    # el signo para customer+outbound y supplier+inbound.
    # Usamos x_bkp_write_off_amount como sentinel: si existe, el pago es pre-refactor.
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
            "account_payment_pro: [step 9] fixed unreconciled_amount sign (%s rows)",
            cr.rowcount,
        )

    # ── 10. Validación ────────────────────────────────────────────────────────
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


def _populate_counterpart_currency_id(cr):
    """Pobla counterpart_currency_id para registros que lo tienen en NULL.

    Sigue la misma lógica que _compute_counterpart_currency_id del modelo,
    ejecutada en 5 pasos ordenados por prioridad (cada paso solo toca NULLs).
    """
    # 4.1: Transferencias internas → moneda del diario destino (o compañía)
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = COALESCE(dj.currency_id, rc.currency_id)
        FROM account_journal dj
        JOIN res_company rc ON rc.id = dj.company_id
        WHERE ap.is_internal_transfer = TRUE
          AND ap.destination_journal_id = dj.id
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [step 4.1] counterpart_currency_id for internal transfers (%s rows)",
        cr.rowcount,
    )

    # 4.2: Pagos normales con cuenta que fuerza moneda → usar moneda de la cuenta
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = aa.currency_id
        FROM account_account aa
        WHERE ap.is_internal_transfer = FALSE
          AND ap.destination_account_id = aa.id
          AND aa.currency_id IS NOT NULL
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [step 4.2] counterpart_currency_id from account currency (%s rows)",
        cr.rowcount,
    )

    # 4.3: Pagos con reconcile_on_company_currency = True → moneda de compañía
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = rc.currency_id
        FROM res_company rc
        WHERE ap.is_internal_transfer = FALSE
          AND ap.company_id = rc.id
          AND rc.reconcile_on_company_currency = TRUE
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [step 4.3] counterpart_currency_id with reconcile mode (%s rows)",
        cr.rowcount,
    )

    # 4.4: Usa moneda de las líneas a pagar si solo hay una moneda
    cr.execute("""
        WITH payment_line_currencies AS (
            SELECT
                ap.id AS payment_id,
                MIN(aml.currency_id) AS min_currency,
                MAX(aml.currency_id) AS max_currency
            FROM account_payment ap
            JOIN res_company rc ON rc.id = ap.company_id
            JOIN account_move_line_payment_to_pay_rel rel ON rel.payment_id = ap.id
            JOIN account_move_line aml ON aml.id = rel.to_pay_line_id
            WHERE ap.is_internal_transfer = FALSE
              AND ap.counterpart_currency_id IS NULL
              AND rc.reconcile_on_company_currency = FALSE
            GROUP BY ap.id
        )
        UPDATE account_payment ap
        SET counterpart_currency_id = plc.min_currency
        FROM payment_line_currencies plc
        WHERE ap.id = plc.payment_id
          AND plc.min_currency = plc.max_currency;
    """)
    _logger.info(
        "account_payment_pro: [step 4.4] counterpart_currency_id from to_pay lines (%s rows)",
        cr.rowcount,
    )

    # 4.5: Fallback final → moneda de compañía
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = rc.currency_id
        FROM res_company rc
        WHERE ap.company_id = rc.id
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [step 4.5] counterpart_currency_id fallback to company (%s rows)",
        cr.rowcount,
    )
