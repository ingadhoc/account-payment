##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""
Migración 19.0.2.6.0 — Resolver colisiones de prefix entre receiptbooks de una
compañía y sus branches, ahora en la etapa ``end``.

Hace el mismo trabajo que ``19.0.2.5.0/post-migration.py``, movido de etapa
porque en una actualización de versión el ``post`` corre antes de que las
branches existan: las compañías recién se parentean en el ``end-migration`` de
``base`` (repo odoo-upgrade), que corre una vez actualizados todos los módulos.
Con el árbol todavía plano ``_resolve_branch_prefix_collisions()`` no encontraba
ninguna branch y el talonario de la sucursal se quedaba con el prefix del padre,
listo para chocar en el nombre del primer pago que se postee.

Los scripts ``end`` corren en orden topológico del grafo, así que este corre
después del de ``base`` y ve el árbol ya armado. Idempotente.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    reassigned = env["account.payment.receiptbook"]._resolve_branch_prefix_collisions()
    _logger.info(
        "Migración 19.0.2.6.0: %d receiptbooks reasignados por colisión de prefix",
        len(reassigned),
    )
