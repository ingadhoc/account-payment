##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""
Migración 19.0.2.5.0 — Resolver colisiones de prefix entre receiptbooks de una
compañía y sus branches.

En 19 una branch comparte los diarios de la padre, así que dos receiptbooks con
el mismo ``(prefix, document_type_id, partner_type)`` dentro del mismo árbol de
compañías generan el mismo nombre de asiento en un mismo diario. Delega en
``account.payment.receiptbook._resolve_branch_prefix_collisions()``, que reasigna
un prefix libre al receiptbook de la branch (conservando el de la raíz) y
resincroniza la numeración. Idempotente.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    reassigned = env["account.payment.receiptbook"]._resolve_branch_prefix_collisions()
    _logger.info("Migración 19.0.2.5.0: %d receiptbooks reasignados por colisión de prefix", len(reassigned))
