"""
Post-migration script for account_payment_pro 19.0.2.11.0
===========================================================

`outstanding_account_id` es stored + computed con
`@api.depends('payment_method_line_id')`, que no incluye
`payment_method_line_id.payment_account_id`. Si la cuenta de liquidez se
completa/cambia en la linea de metodo de pago despues de que ya existen
pagos posteados con cheque, esos pagos quedan con
`outstanding_account_id=False` y la constraint `_check_move_id`
(l10n_latam_check) bloquea el reset a borrador.

Este script backfillea `outstanding_account_id` en los pagos con metodo
cheque que quedaron en False pero cuya linea si tiene cuenta configurada,
forzando el recompute (misma logica que ya usa
`_compute_outstanding_account_id`, sin reescribirla).
"""

import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

# account.payment.method.line codes que requieren cuenta de liquidez
# (l10n_latam_check_ux/models/account_payment.py: check_inbound_codes | check_outbound_codes)
_CHECK_METHOD_CODES = [
    "new_third_party_checks",
    "own_checks",
    "issued_checks",
    "in_third_party_checks",
    "out_third_party_checks",
    "return_third_party_checks",
]


def migrate(cr, version):
    if not version:
        return

    _logger.info("account_payment_pro: running post-migrate for %s", version)

    env = util.env(cr)
    payments = env["account.payment"].search(
        [
            ("outstanding_account_id", "=", False),
            ("payment_method_line_id.code", "in", _CHECK_METHOD_CODES),
            ("payment_method_line_id.payment_account_id", "!=", False),
        ]
    )
    _logger.info(
        "account_payment_pro: backfilling outstanding_account_id on %s check payments",
        len(payments),
    )
    payments.invalidate_recordset(["outstanding_account_id"])
    payments.modified(["payment_method_line_id"])
    payments.flush_recordset(["outstanding_account_id"])
