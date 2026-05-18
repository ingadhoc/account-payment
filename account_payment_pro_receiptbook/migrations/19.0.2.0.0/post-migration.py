##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""
Migración 19.0.2.0.0 — Revertir numeración de receiptbooks al modelo basado en
``ir.sequence`` (como estaba en 18.0).

Delega en ``account.payment.receiptbook.action_resync_sequence()``, que crea el
``ir.sequence`` si falta y setea ``number_next`` parseando con regex el sufijo
numérico de los ``account.payment`` existentes. Idempotente: re-correr no
duplica sequences ni reordena la numeración.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})

    receiptbooks = env["account.payment.receiptbook"].with_context(active_test=False).search([])
    _logger.info("Procesando %d receiptbooks para migrar a ir.sequence", len(receiptbooks))

    receiptbooks.action_resync_sequence()
