import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Crea el índice funcional parcial sobre la cola numérica del ``name`` de
    ``account.payment`` para cada receiptbook existente. En instalaciones nuevas
    lo cubre el ``post_init_hook``; en bases ya instaladas, esta migración crea
    los índices faltantes (el SQL es ``CREATE INDEX IF NOT EXISTS``, idempotente)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    receiptbooks = env["account.payment.receiptbook"].search([])
    _logger.info("Creating payment sequence index for %s receiptbooks", len(receiptbooks))
    for receiptbook in receiptbooks:
        receiptbook._create_payment_sequence_index()
