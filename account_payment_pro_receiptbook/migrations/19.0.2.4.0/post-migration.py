##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""
Migración 19.0.2.4.0 — Recomputar ``made_sequence_gap`` de los asientos de
talonario de recibo según la nueva lógica de ``_update_sequence_made_gap``.

Hasta la versión previa el flag de los asientos de receiptbook quedaba en
``False`` de forma incondicional (o lo fijaba la lógica journal-based del core,
que daba falsos positivos). Ahora la detección de huecos se hace acotada al
receiptbook + prefijo, así que los valores guardados pueden estar desactualizados.

Barremos *todos* los asientos con ``receiptbook_id`` (sin filtro de fecha: la
condición es exacta y una ventana temporal solo dejaría asientos viejos mal
marcados) y reaplicamos la detección. Idempotente.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("Running post-migration %s: recompute made_sequence_gap on receiptbook moves", version)

    env = api.Environment(cr, SUPERUSER_ID, {})

    moves = env["account.move"].with_context(active_test=False).search([("receiptbook_id", "!=", False)])
    _logger.info("Recomputando made_sequence_gap en %d asientos de receiptbook", len(moves))

    if moves:
        moves._update_receiptbook_made_sequence_gap()
        env.flush_all()
