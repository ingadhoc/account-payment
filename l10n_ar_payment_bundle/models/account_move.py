import logging

from odoo import models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _auto_init(self):
        res = super()._auto_init()
        # Cubre la carrera entre dos action_post concurrentes que calculan
        # MAX+1 antes de que el otro commitee: _locked_increment retry-on-UniqueViolation
        # repite hasta encontrar un número libre.
        self.env.cr.execute(
            SQL(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS account_move_receiptbook_name_uniq
                ON account_move (receiptbook_id, name)
                WHERE receiptbook_id IS NOT NULL AND name != '/'
                """
            )
        )
        return res

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        """Cuando el move es la contrapartida de un pago con receiptbook, la fuente de
        verdad de la numeración es ``account.payment``, no ``account.move``. Si una
        operación de bundle genera moves auxiliares, esos moves "ensucian" la secuencia
        de account.move y rompen el próximo número (ticket OBA #116908)."""
        self.ensure_one()
        is_payment = self.origin_payment_id or self.env.context.get("is_payment")
        if self.receiptbook_id and is_payment:
            self.env["account.payment"].flush_model(["name", "receiptbook_id"])
            excluded_payment_id = self.origin_payment_id._origin.id or self.origin_payment_id.id or 0
            self.env.cr.execute(
                SQL(
                    r"""
                    SELECT name FROM account_payment
                    WHERE receiptbook_id = %s
                      AND name ~ '\d+$'
                      AND id != %s
                    ORDER BY CAST((regexp_match(name, '\d+$'))[1] AS INTEGER) DESC
                    LIMIT 1
                    """,
                    self.receiptbook_id.id,
                    excluded_payment_id,
                )
            )
            row = self.env.cr.fetchone()
            return row[0] if row else None
        return super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
