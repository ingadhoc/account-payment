"""Vuelve a vincular los cheques a la entrada de los depósitos que los perdieron.

Hasta la 18.0.2.14.0, confirmar de nuevo la entrada de una transferencia de cheques a un diario sin
método de cheques (un banco) le desvinculaba los cheques: la salida quedaba como última operación y
el cheque, sin diario actual. El fix de código evita que vuelva a pasar, pero no repara los
depósitos que ya quedaron así.

Por cada entrada rota:

* se vinculan los cheques de su pago par, por SQL: escribir el many2many por ORM recalcula
  ``amount`` sobre un pago confirmado y puede reescribir un asiento ya conciliado con el extracto;
* se deja su fecha de operación después de la salida, para que vuelva a ser la última operación;
* se recalculan ``current_journal_id`` y ``company_id`` solo de esos cheques;
* se concilia el par de apuntes de la cuenta de transferencias, que volver a borrador desconcilió.

Se saltea, y queda en el log, el depósito cuya salida ya no es la última operación de sus cheques
(hubo movimientos después) o cuyo monto no coincide con el de los cheques.
"""

import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    fecha = "l10n_latam_move_check_ids_operation_date"
    no_vigentes = ("draft", "canceled")

    cr.execute(
        """
        SELECT entrada.id
          FROM account_payment entrada
          JOIN account_payment salida ON salida.id = entrada.paired_internal_transfer_payment_id
         WHERE entrada.is_internal_transfer
           AND entrada.payment_type = 'inbound'
           AND entrada.state NOT IN %s
           AND salida.state NOT IN %s
           AND NOT EXISTS (
                SELECT 1 FROM l10n_latam_check_account_payment_rel rel WHERE rel.payment_id = entrada.id)
           AND EXISTS (
                SELECT 1 FROM l10n_latam_check_account_payment_rel rel WHERE rel.payment_id = salida.id)
        """,
        (no_vigentes, no_vigentes),
    )
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    entradas = env["account.payment"].browse([row[0] for row in cr.fetchall()])

    corregidas = env["account.payment"].browse()
    for entrada in entradas:
        salida = entrada.paired_internal_transfer_payment_id
        cheques = salida.l10n_latam_move_check_ids
        if any(cheque._get_last_operation() != salida for cheque in cheques):
            _logger.warning(
                "Depósito %s salteado: la salida %s ya no es la última operación", entrada.name, salida.name
            )
            continue
        if entrada.currency_id.compare_amounts(entrada.amount, sum(cheques.mapped("amount"))):
            _logger.warning("Depósito %s salteado: el monto no coincide con el de los cheques", entrada.name)
            continue

        with cr.savepoint():
            cr.executemany(
                "INSERT INTO l10n_latam_check_account_payment_rel (payment_id, check_id) VALUES (%s, %s)",
                [(entrada.id, cheque.id) for cheque in cheques],
            )
            env.invalidate_all()
            if not entrada[fecha] or entrada[fecha] <= salida[fecha]:
                entrada[fecha] = salida[fecha] + timedelta(seconds=1)
            cheques._compute_current_journal()
            cheques._compute_company_id()

            lineas = (salida.move_id.line_ids | entrada.move_id.line_ids).filtered(
                lambda line: line.account_id == salida.destination_account_id and not line.reconciled
            )
            if len(lineas) == 2 and lineas.company_currency_id.is_zero(sum(lineas.mapped("balance"))):
                lineas.reconcile()
            elif lineas:
                _logger.warning("Depósito %s: el par de la cuenta de transferencias no se concilió", entrada.name)
        corregidas |= entrada

    _logger.info(
        "Depósitos de cheques sin cheques en la entrada: %s de %s candidato(s). Corregidos: %s",
        len(corregidas),
        len(entradas),
        ", ".join(filter(None, corregidas.mapped("name"))) or "ninguno",
    )
