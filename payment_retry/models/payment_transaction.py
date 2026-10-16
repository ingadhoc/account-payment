import logging
from datetime import datetime

from dateutil import relativedelta
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    asynchronous_process = fields.Boolean("asynchronous_process")

    @api.model
    def cron_asynchronous_process(self, retry_limit_days=4):
        retry_limit_date = datetime.now() - relativedelta.relativedelta(days=4)
        tx_ids = self.env["payment.transaction"].search(
            [
                ("state", "=", "draft"),
                ("operation", "!=", "validation"),
                ("asynchronous_process", "=", True),
                ("create_date", ">=", retry_limit_date),
                # Already sent: the provider answer waits in payment.data to be processed.
                ("payment_data_ids", "=", False),
            ]
        )
        self.env["ir.cron"]._commit_progress(remaining=len(tx_ids))
        for tx_id in tx_ids:
            try:
                if tx_id.state == "draft" and not tx_id.payment_data_ids:
                    tx_id._send_payment_request()
                self.env["ir.cron"]._commit_progress(1)
            except Exception as exp:
                self.env.cr.rollback()  # pragma pylint: disable=invalid-rollback
                tx_id.with_context(payment_safe_write=True).state = "error"
                _logger.error(_("Error al enviar request tx id %i: %s") % (tx_id.id, str(exp)))
                self.env["ir.cron"]._commit_progress(1)

    def _post_process_with_lock(self):
        """Keep the transactions still waiting to be sent out of the post-processing.

        `payment`'s post-processing cron does not filter by state, so it also locks and writes the
        draft transactions `cron_asynchronous_process` is sending. When both write the same row,
        under REPEATABLE READ the one committing last fails. A draft transaction has nothing to
        post-process, and comes back here once it reaches a final state.
        """
        waiting_txs = self.filtered(lambda tx: tx.asynchronous_process and tx.state == "draft")
        return super(PaymentTransaction, self - waiting_txs)._post_process_with_lock()
