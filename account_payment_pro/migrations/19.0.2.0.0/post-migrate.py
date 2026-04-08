"""
Post-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Se ejecuta después de que el ORM cargó el nuevo código del módulo.

Qué supone:
  - El pre-migrate creó columnas x_bkp_* con los valores originales.
  - counterpart_rate fue renombrado desde counterpart_exchange_rate (pre-migrate)
    con valores en formato viejo. accounting_rate y counterpart_currency_amount
    fueron pre-creados con defaults seguros (1.0 y amount respectivamente).

Qué garantiza al terminar:
  - accounting_rate contiene el rate efectivo A/C para cada pago.
  - counterpart_rate contiene el rate histórico B1/A (1 / viejo counterpart_exchange_rate).
  - counterpart_currency_id poblado para todos los pagos (NULLs resueltos).
  - write_off_amount convertido de company_currency a destination_currency.
  - unreconciled_amount convertido de company_currency a destination_currency
    y con signo corregido para los escenarios invertidos.
  - counterpart_currency_amount pre-poblado y siempre positivo.

Re-ejecutable: todas las transformaciones leen de x_bkp_* (inmutables) y
filtran por x_bkp_migrated = TRUE (sentinel del pre-migrate). Esto garantiza
que pagos creados después de la migración nunca son tocados, aunque el post
se vuelva a correr.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    has_bkp_counterpart = openupgrade.column_exists(cr, "account_payment", "x_bkp_counterpart_exchange_rate")
    has_bkp_force = openupgrade.column_exists(cr, "account_payment", "x_bkp_force_amount_company_currency")
    has_bkp_write_off = openupgrade.column_exists(cr, "account_payment", "x_bkp_write_off_amount")
    has_bkp_unreconciled = openupgrade.column_exists(cr, "account_payment", "x_bkp_unreconciled_amount")

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 1: accounting_rate
    # ══════════════════════════════════════════════════════════════════════════
    # accounting_rate = A/C (formato Odoo: _get_conversion_rate(C, A))
    # Se computa en 3 sub-pasos ordenados por prioridad.

    # 1a) Misma moneda (A == C) → rate = 1.0
    cr.execute("""
        UPDATE account_payment ap
        SET accounting_rate = 1.0
        FROM res_company rc
        WHERE rc.id = ap.company_id
          AND ap.x_bkp_migrated = TRUE
          AND ap.currency_id = rc.currency_id;
    """)
    _logger.info(
        "account_payment_pro: [1a] accounting_rate = 1.0 for same-currency (%s rows)",
        cr.rowcount,
    )

    # 1b) Con cotización forzada (A ≠ C) → rate = amount / force
    if has_bkp_force:
        cr.execute("""
            UPDATE account_payment ap
            SET accounting_rate = ap.amount / ap.x_bkp_force_amount_company_currency
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.x_bkp_migrated = TRUE
              AND ap.currency_id != rc.currency_id
              AND ap.x_bkp_force_amount_company_currency IS NOT NULL
              AND ap.x_bkp_force_amount_company_currency != 0
              AND ap.amount IS NOT NULL
              AND ap.amount != 0;
        """)
        _logger.info(
            "account_payment_pro: [1b] accounting_rate from force backup (%s rows)",
            cr.rowcount,
        )

    # 1c) Moneda diferente sin force → tasa histórica desde res_currency_rate
    # _get_conversion_rate(C, A) = A_rate / C_rate.
    # C_rate es siempre 1.0 para la moneda de la compañía, así que = A_rate.
    cr.execute(  # pylint: disable=sql-injection
        """
        UPDATE account_payment ap
        SET accounting_rate = COALESCE(
            (SELECT r.rate
             FROM res_currency_rate r
             WHERE r.currency_id = ap.currency_id
               AND r.company_id = ap.company_id
               AND r.name <= COALESCE(ap.date, CURRENT_DATE)
             ORDER BY r.name DESC
             LIMIT 1),
            1.0
        )
        FROM res_company rc
        WHERE rc.id = ap.company_id
          AND ap.x_bkp_migrated = TRUE
          AND ap.currency_id != rc.currency_id
          AND (NOT %(has_bkp_force)s
               OR ap.x_bkp_force_amount_company_currency IS NULL
               OR ap.x_bkp_force_amount_company_currency = 0);
    """
        % {"has_bkp_force": has_bkp_force}
    )
    _logger.info(
        "account_payment_pro: [1c] accounting_rate from currency rates (%s rows)",
        cr.rowcount,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 2: counterpart_rate — restaurar rate histórico
    # ══════════════════════════════════════════════════════════════════════════
    # Valor viejo = C/B1 (user-friendly, ej: 1428 ARS/USD).
    # Valor nuevo = B1/A (Odoo nativo). Como en caso (a) A=C → B1/A = 1/(C/B1).
    if has_bkp_counterpart:
        cr.execute("""
            UPDATE account_payment
            SET counterpart_rate = 1.0 / x_bkp_counterpart_exchange_rate
            WHERE x_bkp_migrated = TRUE
              AND x_bkp_counterpart_exchange_rate IS NOT NULL
              AND x_bkp_counterpart_exchange_rate != 0;
        """)
        _logger.info(
            "account_payment_pro: [2] counterpart_rate from backup (%s rows)",
            cr.rowcount,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 3: Fix caso (b) — pagos con counterpart definida pero A ≠ C
    # ══════════════════════════════════════════════════════════════════════════
    # En el código viejo _use_counterpart_currency() requería A == C.
    # Cuando A ≠ C, la counterpart_currency_id existía pero se IGNORABA en el
    # asiento. Limpiar: B1 = A, counterpart_rate = 1.0.
    # Esto cubre también el caso "both" (tenía counterpart + force simultáneamente,
    # que eran condiciones mutuamente excluyentes en el código viejo).
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = ap.currency_id,
            counterpart_rate = 1.0
        FROM res_company rc
        WHERE rc.id = ap.company_id
          AND ap.x_bkp_migrated = TRUE
          AND ap.currency_id != rc.currency_id
          AND ap.counterpart_currency_id IS NOT NULL
          AND ap.counterpart_currency_id != ap.currency_id;
    """)
    _logger.info(
        "account_payment_pro: [3] fixed case (b) — counterpart ignored when A!=C (%s rows)",
        cr.rowcount,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 4: counterpart_currency_id — poblar NULLs
    # ══════════════════════════════════════════════════════════════════════════
    _populate_counterpart_currency_id(cr)

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 5: counterpart_rate para registros recién poblados
    # ══════════════════════════════════════════════════════════════════════════
    # Registros que no tenían counterpart_exchange_rate (x_bkp NULL/0) pero
    # ahora tienen counterpart_currency_id poblado por el paso 4.
    # counterpart_rate sigue con el default 1.0; corregirlo según B1 vs A vs C.

    # 5a) B1 = A → counterpart_rate = 1.0
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_rate = 1.0
        WHERE ap.x_bkp_migrated = TRUE
          AND (ap.counterpart_rate IS NULL OR ap.counterpart_rate = 0)
          AND ap.counterpart_currency_id IS NOT NULL
          AND ap.counterpart_currency_id = ap.currency_id;
    """)
    _logger.info(
        "account_payment_pro: [5a] counterpart_rate = 1.0 for B1=A (%s rows)",
        cr.rowcount,
    )

    # 5b) B1 = C y A ≠ C → counterpart_rate = 1/accounting_rate (= C/A)
    bkp_null_condition = (
        "(ap.x_bkp_counterpart_exchange_rate IS NULL OR ap.x_bkp_counterpart_exchange_rate = 0)"
        if has_bkp_counterpart
        else "TRUE"
    )
    cr.execute(  # pylint: disable=sql-injection
        """
        UPDATE account_payment ap
        SET counterpart_rate = 1.0 / ap.accounting_rate
        FROM res_company rc
        WHERE rc.id = ap.company_id
          AND ap.x_bkp_migrated = TRUE
          AND %(bkp_null_cond)s
          AND ap.counterpart_currency_id = rc.currency_id
          AND ap.currency_id != rc.currency_id
          AND ap.accounting_rate IS NOT NULL
          AND ap.accounting_rate != 0;
    """
        % {"bkp_null_cond": bkp_null_condition}
    )
    _logger.info(
        "account_payment_pro: [5b] counterpart_rate for B1=C newly populated (%s rows)",
        cr.rowcount,
    )

    # 5c) B1 ≠ A y B1 ≠ C → rate desde res_currency_rate
    # _get_conversion_rate(A, B1) = B1_rate / A_rate
    cr.execute(  # pylint: disable=sql-injection
        """
        UPDATE account_payment ap
        SET counterpart_rate = COALESCE(
            (SELECT r.rate FROM res_currency_rate r
             WHERE r.currency_id = ap.counterpart_currency_id
               AND r.company_id = ap.company_id
               AND r.name <= COALESCE(ap.date, CURRENT_DATE)
             ORDER BY r.name DESC LIMIT 1)
            /
            NULLIF(
                (SELECT r.rate FROM res_currency_rate r
                 WHERE r.currency_id = ap.currency_id
                   AND r.company_id = ap.company_id
                   AND r.name <= COALESCE(ap.date, CURRENT_DATE)
                 ORDER BY r.name DESC LIMIT 1),
                0
            ),
            1.0
        )
        FROM res_company rc
        WHERE rc.id = ap.company_id
          AND ap.x_bkp_migrated = TRUE
          AND %(bkp_null_cond)s
          AND ap.counterpart_currency_id != ap.currency_id
          AND ap.counterpart_currency_id != rc.currency_id;
    """
        % {"bkp_null_cond": bkp_null_condition}
    )
    _logger.info(
        "account_payment_pro: [5c] counterpart_rate for B1!=A!=C newly populated (%s rows)",
        cr.rowcount,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 6: write_off_amount — convertir de C a destination_currency
    # ══════════════════════════════════════════════════════════════════════════
    # Factor = counterpart_rate × accounting_rate = (B1/A) × (A/C) = B1/C.
    # Cuando reconcile_on_company_currency = True, destination = C → factor = 1.
    # Cuando B1 = C el factor se auto-neutraliza a 1.0.
    if has_bkp_write_off:
        cr.execute("""
            UPDATE account_payment ap
            SET write_off_amount = ap.x_bkp_write_off_amount
                * CASE
                    WHEN rc.reconcile_on_company_currency IS TRUE THEN 1.0
                    ELSE COALESCE(
                        NULLIF(ap.counterpart_rate * ap.accounting_rate, 0),
                        1.0
                    )
                  END
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.x_bkp_migrated = TRUE
              AND ap.x_bkp_write_off_amount IS NOT NULL
              AND ap.x_bkp_write_off_amount != 0;
        """)
        _logger.info(
            "account_payment_pro: [6] write_off_amount converted to destination_currency (%s rows)",
            cr.rowcount,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 7: unreconciled_amount — convertir moneda + corregir signo
    # ══════════════════════════════════════════════════════════════════════════
    # Dos cambios simultáneos:
    # a) Moneda: company_currency → destination_currency (mismo factor que write_off)
    # b) Signo: selected_debt cambió de usar partner_type a payment_type.
    #    Invertir para: customer+outbound y supplier+inbound.
    if has_bkp_unreconciled:
        cr.execute("""
            UPDATE account_payment ap
            SET unreconciled_amount = ap.x_bkp_unreconciled_amount
                * CASE
                    WHEN rc.reconcile_on_company_currency IS TRUE THEN 1.0
                    ELSE COALESCE(
                        NULLIF(ap.counterpart_rate * ap.accounting_rate, 0),
                        1.0
                    )
                  END
                * CASE
                    WHEN (ap.partner_type = 'customer' AND ap.payment_type = 'outbound')
                      OR (ap.partner_type = 'supplier' AND ap.payment_type = 'inbound')
                    THEN -1.0
                    ELSE 1.0
                  END
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.x_bkp_migrated = TRUE
              AND ap.x_bkp_unreconciled_amount IS NOT NULL
              AND ap.x_bkp_unreconciled_amount != 0;
        """)
        _logger.info(
            "account_payment_pro: [7] unreconciled_amount converted + sign fixed (%s rows)",
            cr.rowcount,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 8: counterpart_currency_amount — poblar
    # ══════════════════════════════════════════════════════════════════════════
    # Fórmula = _compute_counterpart_currency_amount:
    #   A ≠ B1 → amount × counterpart_rate  |  A == B1 → amount
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
        WHERE x_bkp_migrated = TRUE;
    """)
    _logger.info(
        "account_payment_pro: [8] counterpart_currency_amount populated (%s rows)",
        cr.rowcount,
    )

    # ── 8b: asegurar que sea siempre positivo ─────────────────────────────────
    cr.execute("""
        UPDATE account_payment
        SET counterpart_currency_amount = ABS(counterpart_currency_amount)
        WHERE x_bkp_migrated = TRUE
          AND counterpart_currency_amount < 0;
    """)
    if cr.rowcount:
        _logger.info(
            "account_payment_pro: [8b] fixed negative counterpart_currency_amount (%s rows)",
            cr.rowcount,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 9: Validación
    # ══════════════════════════════════════════════════════════════════════════
    cr.execute("""
        SELECT COUNT(*) FROM account_payment
        WHERE x_bkp_migrated = TRUE
          AND state != 'draft'
          AND (accounting_rate IS NULL OR counterpart_rate IS NULL
               OR counterpart_currency_id IS NULL);
    """)
    count = cr.fetchone()[0]
    if count:
        _logger.warning(
            "account_payment_pro: %d posted payments with NULL accounting_rate, "
            "counterpart_rate or counterpart_currency_id — review migration.",
            count,
        )
    else:
        _logger.info("account_payment_pro: all posted payments have rates and " "counterpart_currency_id populated.")


def _populate_counterpart_currency_id(cr):
    """Pobla counterpart_currency_id para registros que lo tienen en NULL.

    Sigue la misma lógica que _compute_counterpart_currency_id del nuevo modelo,
    ejecutada en 4 pasos ordenados por prioridad (cada paso solo toca NULLs).
    """
    # 4.1: Transferencias internas → moneda del diario destino (o compañía)
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = COALESCE(dj.currency_id, rc.currency_id)
        FROM account_journal dj
        JOIN res_company rc ON rc.id = dj.company_id
        WHERE ap.is_internal_transfer IS TRUE
          AND ap.destination_journal_id = dj.id
          AND ap.x_bkp_migrated = TRUE
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [4.1] counterpart_currency_id for internal transfers (%s rows)",
        cr.rowcount,
    )

    # 4.2: Cuenta con moneda forzada distinta a la de la compañía
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = aa.currency_id
        FROM account_account aa, res_company rc
        WHERE ap.destination_account_id = aa.id
          AND rc.id = ap.company_id
          AND aa.currency_id IS NOT NULL
          AND aa.currency_id != rc.currency_id
          AND ap.is_internal_transfer IS NOT TRUE
          AND ap.x_bkp_migrated = TRUE
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [4.2] counterpart_currency_id from account currency (%s rows)",
        cr.rowcount,
    )

    # 4.3: Desde to_pay_move_line_ids cuando hay una sola moneda (sin reconcile)
    cr.execute("""
        WITH payment_currencies AS (
            SELECT
                rel.payment_id,
                MIN(aml.currency_id) AS min_c,
                MAX(aml.currency_id) AS max_c
            FROM account_move_line_payment_to_pay_rel rel
            JOIN account_move_line aml ON aml.id = rel.to_pay_line_id
            JOIN account_payment ap ON ap.id = rel.payment_id
            JOIN res_company rc ON rc.id = ap.company_id
            WHERE ap.counterpart_currency_id IS NULL
              AND ap.is_internal_transfer IS NOT TRUE
              AND ap.x_bkp_migrated = TRUE
              AND rc.reconcile_on_company_currency IS NOT TRUE
            GROUP BY rel.payment_id
        )
        UPDATE account_payment ap
        SET counterpart_currency_id = pc.min_c
        FROM payment_currencies pc
        WHERE ap.id = pc.payment_id
          AND pc.min_c = pc.max_c;
    """)
    _logger.info(
        "account_payment_pro: [4.3] counterpart_currency_id from to_pay lines (%s rows)",
        cr.rowcount,
    )

    # 4.4: Fallback → moneda de compañía (cubre reconcile_on_company_currency y resto)
    cr.execute("""
        UPDATE account_payment ap
        SET counterpart_currency_id = rc.currency_id
        FROM res_company rc
        WHERE ap.company_id = rc.id
          AND ap.x_bkp_migrated = TRUE
          AND ap.counterpart_currency_id IS NULL;
    """)
    _logger.info(
        "account_payment_pro: [4.4] counterpart_currency_id fallback to company currency (%s rows)",
        cr.rowcount,
    )
