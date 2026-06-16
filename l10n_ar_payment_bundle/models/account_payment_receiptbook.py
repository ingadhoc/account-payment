import logging

from odoo import api, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class AccountPaymentReceiptbook(models.Model):
    _inherit = "account.payment.receiptbook"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._create_payment_sequence_index()
        return records

    def unlink(self):
        for rec in self:
            rec._drop_payment_sequence_index()
        return super().unlink()

    def _payment_sequence_index_name(self):
        self.ensure_one()
        return f"l10n_ar_pb_recbook_{self.id}_seq_idx"

    def _create_payment_sequence_index(self):
        """Índice funcional parcial sobre la cola numérica del ``name`` de
        ``account.payment`` para este receiptbook. Acelera el MAX/ORDER BY que
        usa _get_last_sequence en account_move."""
        self.ensure_one()
        index_name = self._payment_sequence_index_name()
        self.env.cr.execute(
            SQL(
                r"""
                CREATE INDEX IF NOT EXISTS %s
                ON account_payment ((CAST((regexp_match(name, '\d+$'))[1] AS INTEGER)))
                WHERE receiptbook_id = %s AND name ~ '\d+$'
                """,
                SQL.identifier(index_name),
                self.id,
            )
        )

    def _drop_payment_sequence_index(self):
        self.ensure_one()
        index_name = self._payment_sequence_index_name()
        self.env.cr.execute(SQL("DROP INDEX IF EXISTS %s", SQL.identifier(index_name)))
