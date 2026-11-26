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

El barrido se hace en SQL y no con ``_update_receiptbook_made_sequence_gap()``.
``made_sequence_gap`` es un boolean plano de housekeeping (sin tracking, sin
inverse, sin depends), pero asignarlo por ORM dispara ``account.move.write()``
y con él el override de Purchase, que hace
``move.mapped('line_ids.purchase_line_id.order_id')`` por cada asiento. Sobre un
recordset del tamaño de toda la tabla eso materializa en memoria los ids de
todas las ``account.move.line`` de la base y termina en ``MemoryError``.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Un asiento hace hueco cuando falta el número inmediatamente anterior dentro
# del mismo receiptbook + prefijo. Los no posteados que ya tomaron número se
# marcan siempre. El LEFT JOIN busca ese predecesor sin filtrar por estado (un
# asiento cancelado igual ocupa el número).
_RECOMPUTE_MADE_SEQUENCE_GAP = """
    WITH rb AS (
        SELECT id,
               receiptbook_id,
               COALESCE(sequence_prefix, '') AS prefix,
               COALESCE(sequence_number, 0) AS sequence_number,
               state
          FROM account_move
         WHERE receiptbook_id IS NOT NULL
    ),
    computed AS (
        SELECT DISTINCT
               m.id,
               CASE
                   WHEN m.sequence_number <> 0 AND m.state <> 'posted' THEN TRUE
                   WHEN m.sequence_number > 1 AND p.id IS NULL THEN TRUE
                   ELSE FALSE
               END AS made_gap
          FROM rb m
          LEFT JOIN rb p
                 ON p.receiptbook_id = m.receiptbook_id
                AND p.prefix = m.prefix
                AND p.sequence_number = m.sequence_number - 1
    )
    UPDATE account_move am
       SET made_sequence_gap = c.made_gap
      FROM computed c
     WHERE am.id = c.id
       AND am.made_sequence_gap IS DISTINCT FROM c.made_gap
"""


def migrate(cr, version):
    _logger.info("Running post-migration %s: recompute made_sequence_gap on receiptbook moves", version)

    env = api.Environment(cr, SUPERUSER_ID, {})
    # ``receiptbook_id`` es related stored y ``sequence_prefix`` / ``sequence_number``
    # son computados stored: puede haber recomputes pendientes que el SQL no vería.
    env.flush_all()

    cr.execute(_RECOMPUTE_MADE_SEQUENCE_GAP)
    _logger.info("made_sequence_gap actualizado en %d asientos de receiptbook", cr.rowcount)

    # Pisamos columnas por fuera del ORM.
    env.invalidate_all()
