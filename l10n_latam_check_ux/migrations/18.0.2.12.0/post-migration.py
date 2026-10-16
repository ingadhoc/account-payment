"""Corrige las cadenas de operaciones de cheques que quedaron invertidas.

Tickets 126339 / 126474, tarea 73306. El fix de código de la 18.0.2.11.0 evita que vuelva a
pasar, pero no repara las cadenas ya invertidas.

DETECCIÓN POR SÍNTOMA, NO POR FECHAS
    Hasta la 18.0.2.11.0 el default del campo de fecha de operación se evaluaba una sola vez al
    importar el módulo, así que todos los pagos preexistentes quedaron con el mismo timestamp.
    Esos cheques están EMPATADOS, no invertidos, y el desempate por ``id`` de
    ``_get_last_operation()`` los ordena bien: compararlos por fecha marcaría cientos de cheques
    sanos. Se corrige solo donde el invariante está roto — el pago donde el cheque NACE no puede
    ser la última operación de la cadena si después hubo otras.

``current_journal_id`` y ``company_id`` se recalculan solo sobre los cheques alcanzados: son
stored y su ``depends`` no incluye la fecha, así que reordenar no los dispara, pero un recompute
masivo movería cheques que hoy están bien (ver ticket 123455).
"""

import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    fecha = "l10n_latam_move_check_ids_operation_date"
    no_vigentes = ("draft", "canceled")

    # Prefiltro para no recorrer todos los cheques de la base. Es conservador: si el nacimiento es
    # el último por (fecha, id), toda operación posterior cumple fecha <= fecha_nacimiento, así que
    # ninguna cadena invertida se escapa. Puede traer empates de más, que el ORM descarta abajo.
    cr.execute(
        f"""
        SELECT DISTINCT check_rel.check_id
          FROM l10n_latam_check_account_payment_rel check_rel
          JOIN l10n_latam_check chk ON chk.id = check_rel.check_id
          JOIN account_payment nacimiento ON nacimiento.id = chk.payment_id
          JOIN account_payment posterior ON posterior.id = check_rel.payment_id
         WHERE posterior.id != nacimiento.id
           AND nacimiento.state NOT IN %s
           AND posterior.state NOT IN %s
           AND nacimiento.{fecha} IS NOT NULL
           AND posterior.{fecha} IS NOT NULL
           AND posterior.{fecha} <= nacimiento.{fecha}
        """,
        (no_vigentes, no_vigentes),
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    candidatos = env["l10n_latam.check"].browse([row[0] for row in cr.fetchall()])

    # La cadena está invertida cuando el nacimiento sigue siendo la última operación. No hace falta
    # exigir aparte que existan posteriores: el SQL ya devuelve solo cheques que tienen al menos una
    # vigente. Se filtra antes de escribir porque un pago puede llevar varios cheques y corregir su
    # fecha ordena todas esas cadenas de una vez: evaluar el síntoma dentro del loop dejaría al
    # segundo cheque afuera del recompute, con la cadena bien y el cheque todavía en cartera.
    corregidos = candidatos.filtered(lambda c: c._get_last_operation() == c.payment_id)

    tocados = env["account.payment"].browse()
    for check in corregidos:
        previa = check.payment_id[fecha]
        # tracking_disable: account.payment es mail.thread, y cada write snapshotea todos sus
        # campos trackeados —algunos computados sobre apuntes contables—, no solo el que se toca.
        operaciones = (check.operation_ids - check.payment_id).with_context(tracking_disable=True)
        vigentes = operaciones.filtered(lambda p: p.state not in no_vigentes and p[fecha])
        for payment in vigentes.sorted(key=lambda p: (p[fecha], p.id)):
            if payment[fecha] <= previa:
                nueva = previa + timedelta(seconds=1)
                _logger.info("Cheque %s: operación %s pasa de %s a %s", check.name, payment.name, payment[fecha], nueva)
                payment[fecha] = nueva
                tocados |= payment
            previa = payment[fecha]

    # Un pago puede llevar varios cheques, así que moverle la fecha reordena todas esas cadenas,
    # no solo la que motivó la escritura. El recompute va sobre todas: si se limitara a
    # `corregidos`, un cheque vecino quedaría con la cadena movida y el diario actual viejo.
    afectados = corregidos | tocados.l10n_latam_move_check_ids
    afectados._compute_current_journal()
    afectados._compute_company_id()

    _logger.info(
        "Cadenas de cheques invertidas: %s de %s candidato(s). Corregidos: %s",
        len(corregidos),
        len(candidatos),
        ", ".join(filter(None, corregidos.mapped("name"))) or "ninguno",
    )
    # Mover un pago compartido puede invertir la cadena de un cheque vecino que estaba sana. No se
    # corrige en cascada; se avisa para que no pase en silencio. Acá sí hay que exigir que existan
    # posteriores vigentes: los vecinos no pasaron por el filtro del SQL.
    restantes = afectados.filtered(
        lambda c: c._get_last_operation() == c.payment_id
        and (c.operation_ids - c.payment_id).filtered(lambda p: p.state not in no_vigentes and p[fecha])
    )
    if restantes:
        _logger.warning(
            "Quedaron %s cheque(s) con la cadena invertida, revisar a mano: %s",
            len(restantes),
            ", ".join(filter(None, restantes.mapped("name"))),
        )
