"""
Post-migration script for account_payment_pro 19.0.2.2.0
=========================================================

Qué supone:
  - El módulo ya fue actualizado a 19.0.2.2.0.

Qué garantiza al terminar:
  - counterpart_currency_amount es siempre positivo (= amount × counterpart_rate).
  - unreconciled_amount es siempre positivo o cero.

Contexto:
  En versiones anteriores al refactor tri-monetario, ambos campos se almacenaban
  con signo negativo en los siguientes escenarios:
    - partner_type = customer + payment_type = outbound
    - partner_type = supplier + payment_type = inbound
  Tras el refactor, amount (nativo de Odoo) es siempre positivo y counterpart_rate
  también, por lo que counterpart_currency_amount debe serlo. Lo mismo aplica a
  unreconciled_amount, que deriva de selected_debt (ahora siempre positivo).
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # counterpart_currency_amount: debe ser siempre positivo (= amount × rate)
    cr.execute("""
        UPDATE account_payment
        SET counterpart_currency_amount = ABS(counterpart_currency_amount)
        WHERE counterpart_currency_amount < 0;
    """)
    _logger.info(
        "account_payment_pro: fixed counterpart_currency_amount sign (%s rows)",
        cr.rowcount,
    )

    # unreconciled_amount: solo negamos registros migrados desde el código viejo
    # (identificados por tener valor en la columna de backup x_bkp_write_off_amount
    # del script 19.0.2.0.0 — write_off_amount era campo almacenado, por lo que
    # su backup existe para TODOS los pagos previos a la migración, incluso
    # los de moneda única con write_off = 0).
    # Solo aplicamos en los escenarios donde el signo cambió por el refactor:
    #   - customer + outbound (selected_debt era negativo antes, ahora es positivo)
    #   - supplier + inbound  (idem)
    # No usamos ABS porque el usuario puede haber ingresado legítimamente un valor
    # en cualquier dirección (avance mayor o menor que la deuda seleccionada).
    # counterpart_currency_amount NO se corrige aquí: era compute sin store=True
    # en el código viejo, y el ORM lo computa correctamente al cargar el módulo.
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
