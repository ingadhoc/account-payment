from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        super()._post_process()

        # Core cancels the payment while the transaction is draft, cancel or error: when it
        # is confirmed later, recover that payment too, as no new one is created
        for tx in self.filtered(
            lambda t: t.state == "done" and t.payment_id and t.payment_id.state in ("draft", "canceled")
        ):
            # Si el pago relacionado a la trasaccion esta en draft y coinciden los datos
            # lo publico y concilio
            # No agrego este if al filtered porque seria iligible. El 99.9% de los casos el if es True
            if tx.payment_id.currency_id == tx.currency_id and tx.payment_id.amount == abs(tx.amount):
                if tx.payment_id.state == "canceled":
                    tx.payment_id.action_draft()
                tx.payment_id.action_post()
                if tx.invoice_ids:
                    (tx.payment_id.move_id.line_ids + tx.invoice_ids.line_ids).filtered(
                        lambda line: line.account_id == tx.payment_id.destination_account_id and not line.reconciled
                    ).reconcile()
