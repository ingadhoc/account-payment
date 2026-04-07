"""
Pre-migration script for account_payment_pro 19.0.2.0.0
=========================================================

Qué supone:
  - Existe la tabla account_payment con las columnas del modelo anterior.

Qué garantiza al terminar:
  - Las columnas que se eliminan o transforman tienen backup con prefijo x_bkp_.
  - Los datos originales quedan preservados para que el post-migrate los use.
  - Las nuevas columnas almacenadas (accounting_rate, counterpart_rate,
    counterpart_currency_amount) existen y están pre-pobladas para evitar
    que el ORM encole un recompute masivo al cargar el módulo nuevo (ADR-009).
  - No se hacen transformaciones finales aquí; el post-migrate ajusta
    valores desde los backups.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ── 1. Backup de columnas originales ──────────────────────────────────────
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

    # ── 2. Renombrar counterpart_exchange_rate → counterpart_rate ─────────────
    # Evita que el ORM cree la columna como si fuera un campo nuevo y encole
    # recompute para todos los registros. Los valores quedan en formato viejo
    # (user-friendly); el post-migrate los invierte a formato Odoo nativo.
    if openupgrade.column_exists(cr, "account_payment", "counterpart_exchange_rate"):
        openupgrade.rename_columns(cr, {"account_payment": [("counterpart_exchange_rate", "counterpart_rate")]})
        # Default 1.0 para registros sin counterpart currency (NULL/0)
        cr.execute("""
            UPDATE account_payment
            SET counterpart_rate = 1.0
            WHERE counterpart_rate IS NULL OR counterpart_rate = 0;
        """)
        _logger.info(
            "account_payment_pro: renamed counterpart_exchange_rate → counterpart_rate "
            "(defaulted %s NULL/0 records to 1.0)",
            cr.rowcount,
        )

    # ── 3. Pre-crear accounting_rate ──────────────────────────────────────────
    # Campo nuevo store=True. Si no existe al cargar el módulo, el ORM encola
    # recompute (llama _get_conversion_rate por cada registro = lento).
    if not openupgrade.column_exists(cr, "account_payment", "accounting_rate"):
        cr.execute("ALTER TABLE account_payment ADD COLUMN accounting_rate float8")

        # 3a) Pagos con cotización forzada y A ≠ C → rate = amount / force
        # Solo cuando A ≠ C: si A = C, accounting_rate es siempre 1.0.
        # El force en pagos A=C existía como artefacto de other_currency=True
        # en transferencias internas pero no afecta el rate A/C.
        if openupgrade.column_exists(cr, "account_payment", "force_amount_company_currency"):
            cr.execute("""
                UPDATE account_payment ap
                SET accounting_rate = ap.amount / ap.force_amount_company_currency
                FROM res_company rc
                WHERE rc.id = ap.company_id
                  AND ap.currency_id != rc.currency_id
                  AND ap.force_amount_company_currency IS NOT NULL
                  AND ap.force_amount_company_currency != 0;
            """)
            _logger.info(
                "account_payment_pro: accounting_rate from force (%s rows)",
                cr.rowcount,
            )

        # 3b) Misma moneda (A == C) → rate = 1.0
        cr.execute("""
            UPDATE account_payment ap
            SET accounting_rate = 1.0
            FROM res_company rc
            WHERE rc.id = ap.company_id
              AND ap.currency_id = rc.currency_id
              AND ap.accounting_rate IS NULL;
        """)
        _logger.info(
            "account_payment_pro: accounting_rate = 1.0 for same-currency (%s rows)",
            cr.rowcount,
        )

        # 3c) Moneda diferente sin force → tasa histórica desde res_currency_rate
        # accounting_rate = _get_conversion_rate(C, A) = A_rate / C_rate = A_rate
        # (C_rate es siempre 1.0 para la moneda de la compañía)
        cr.execute("""
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
            WHERE ap.accounting_rate IS NULL;
        """)
        _logger.info(
            "account_payment_pro: accounting_rate from currency rates (%s rows)",
            cr.rowcount,
        )

    # ── 4. Pre-crear counterpart_currency_amount ──────────────────────────────
    # Era compute sin store=True → no existe columna en DB. Ahora es store=True.
    # Pre-crear evita recompute masivo; el post-migrate lo pobla correctamente.
    if not openupgrade.column_exists(cr, "account_payment", "counterpart_currency_amount"):
        cr.execute("ALTER TABLE account_payment ADD COLUMN counterpart_currency_amount numeric")
        _logger.info("account_payment_pro: pre-created counterpart_currency_amount column")
