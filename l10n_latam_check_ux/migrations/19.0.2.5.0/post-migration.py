"""Corrige la compañía de los cheques que quedaron con la de una operación que ya no vale.

Hasta esta versión ``company_id`` seguía siendo el related del core (``payment_id.company_id``) y
``_compute_company_id`` corría solo cuando se lo llamaba a mano, al confirmar una transferencia.
Si después esa transferencia volvía a borrador o se cancelaba, el cheque quedaba con la compañía
de la transferencia: por ejemplo, un cheque de vuelta en el diario de la sucursal pero con la
compañía de la casa central.

Solo se recalculan los cheques con alguna operación en borrador o cancelada, y solo cuando la
compañía guardada no coincide con la de su última operación vigente. Un recompute masivo podría
mover cheques que hoy están bien (ver ticket 123455).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    candidatos = env["l10n_latam.check"].search(
        [
            "|",
            ("operation_ids.state", "in", ("draft", "canceled")),
            ("payment_id.state", "in", ("draft", "canceled")),
        ]
    )
    desfasados = candidatos.filtered(
        lambda check: (check._get_last_operation() or check.payment_id).company_id != check.company_id
    )
    anteriores = {check.id: check.company_id.name for check in desfasados}
    desfasados._compute_company_id()
    for check in desfasados:
        _logger.info(
            "Cheque %s (id %s): compañía %s pasa a %s",
            check.name,
            check.id,
            anteriores[check.id],
            check.company_id.name,
        )
    _logger.info(
        "Compañía de cheques: %s corregido(s) de %s candidato(s)",
        len(desfasados),
        len(candidatos),
    )
