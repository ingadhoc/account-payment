##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models


class PaymentTransaction(models.Model):

    _inherit = 'payment.transaction'

    def _reconcile_after_transaction_done(self):
        return super(PaymentTransaction, self.with_context(
            create_from_website=True))._reconcile_after_transaction_done()

    def _set_transaction_cancel(self):
        # TODO remove in v15
        super()._set_transaction_cancel()
        # Cancel the existing payments moves.
        tx_to_process = self.filtered(lambda tx: tx.state == 'cancel')
        moves = tx_to_process.mapped('payment_id.move_line_ids.move_id')
        moves.filtered(lambda move: move.state == 'posted').button_draft()
        moves.with_context(force_delete=True).unlink()
