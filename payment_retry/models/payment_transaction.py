import logging
from datetime import datetime

from dateutil import relativedelta
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    asynchronous_process = fields.Boolean("asynchronous_process")

    @api.model
    def cron_asynchronous_process(self, tx_limit=10, retry_limit_days=4):
        retry_limit_date = datetime.now() - relativedelta.relativedelta(days=4)
        tx_ids = self.env["payment.transaction"].search(
            [
                ("state", "=", "draft"),
                ("operation", "!=", "validation"),
                ("asynchronous_process", "=", True),
                ("create_date", ">=", retry_limit_date),
            ]
        )
        i = 0
        limit = len(tx_ids)
        for tx_id in tx_ids[0:tx_limit]:
            i += 1
            try:
                self.env["ir.cron"]._notify_progress(done=i, remaining=limit - i)
                if tx_id.state == "draft":
                    tx_id._send_payment_request()
            except Exception as exp:
                self.env.cr.rollback()  # pragma pylint: disable=invalid-rollback
                tx_id.state = "error"
                _logger.error(_("Error al enviar request tx id %i: %s") % (tx_id.id, str(exp)))
                self.env.cr.commit()  # pragma pylint: disable=invalid-commit
        if len(tx_ids) > tx_limit:
            self.env.ref("payment_retry.payment_asynchronous_process")._trigger()

    def _cron_post_process(self):
        """Keep the transactions still waiting to be sent out of the post-processing sweep.

        `payment`'s cron does not filter by state, so it also sweeps the draft transactions
        `cron_asynchronous_process` is sending. Both update the same row and, under REPEATABLE
        READ, the one committing last loses its whole transaction. A draft transaction has
        nothing to post-process, and comes back here once it reaches a final state.
        """
        if self:
            return super()._cron_post_process()
        # Same domain as the overridden method, minus the transactions waiting to be sent.
        retry_limit_date = datetime.now() - relativedelta.relativedelta(days=4)
        txs_to_post_process = self.search(
            [
                ("is_post_processed", "=", False),
                ("last_state_change", ">=", retry_limit_date),
                "|",
                ("asynchronous_process", "=", False),
                ("state", "!=", "draft"),
            ]
        )
        if not txs_to_post_process:
            # An empty recordset makes the overridden method run its own unfiltered search.
            return
        return super(PaymentTransaction, txs_to_post_process)._cron_post_process()
