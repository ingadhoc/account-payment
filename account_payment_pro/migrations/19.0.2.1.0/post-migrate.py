"""
Post-migration script for account_payment_pro 19.0.2.1.0
=========================================================

Popula counterpart_currency_id  para registros
existentes que quedaron en NULL después de la migración 19.0.2.0.0.

Qué supone:
  - Los campos counterpart_currency_id  existen
    pero pueden estar en NULL en registros creados antes de la migración.

Qué garantiza al terminar:
  - Todos los pagos tienen counterpart_currency_id poblado siguiendo
    la lógica del compute del modelo.

Re-ejecutable: usa WHERE ... IS NULL por lo que no sobreescribe valores
ya existentes.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ── 1. counterpart_currency_id: compute según lógica del modelo ────────
    # Paso 1.1: Transferencias internas →
    # moneda del diario destino (o compañía)
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = COALESCE(
            dj.currency_id,
            rc.currency_id
        )
        FROM account_journal dj
        JOIN res_company rc ON rc.id = ap.company_id
        WHERE ap.is_internal_transfer = TRUE
          AND ap.destination_journal_id = dj.id
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: counterpart_currency_id for internal " "transfers (%s rows)",
        cr.rowcount,
    )

    # Paso 1.2: Pagos normales con cuenta que fuerza moneda →
    # usar moneda de la cuenta
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
        "account_payment_pro: counterpart_currency_id from account " "currency (%s rows)",
        cr.rowcount,
    )

    # Paso 1.3: Pagos normales con reconcile_on_company_currency = True →
    # mantener moneda de compañía si ya está poblado,
    # sino usar moneda de compañía
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
        "account_payment_pro: counterpart_currency_id with reconcile " "mode (%s rows)",
        cr.rowcount,
    )

    # Paso 1.4: Pagos normales sin reconcile_on_company_currency →
    # usar moneda de las líneas a pagar si solo hay una moneda
    cr.execute("""
        WITH payment_line_currencies AS (
            SELECT
                ap.id AS payment_id,
                MIN(aml.currency_id) AS min_currency,
                MAX(aml.currency_id) AS max_currency
            FROM account_payment ap
            JOIN res_company rc
                ON rc.id = ap.company_id
            JOIN account_move_line_payment_to_pay_rel rel
                ON rel.payment_id = ap.id
            JOIN account_move_line aml
                ON aml.id = rel.to_pay_line_id
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
        "account_payment_pro: counterpart_currency_id from to_pay " "lines (%s rows)",
        cr.rowcount,
    )

    # Paso 1.5: Fallback final →
    # cualquier pago que aún tenga NULL usa moneda de compañía
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = rc.currency_id
        FROM res_company rc
        WHERE ap.company_id = rc.id
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: counterpart_currency_id fallback to " "company (%s rows)",
        cr.rowcount,
    )
