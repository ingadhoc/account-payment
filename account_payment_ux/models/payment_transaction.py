from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        super()._post_process()

        for tx in self.filtered(lambda t: t.state == "done" and t.payment_id and t.payment_id.state == "draft"):
            # Si el pago relacionado a la trasaccion esta en draft y coinciden los datos
            # lo publico y concilio
            # No agrego este if al filtered porque seria iligible. El 99.9% de los casos el if es True
            if tx.payment_id.currency_id == tx.currency_id and tx.payment_id.amount == abs(tx.amount):
                tx.payment_id.action_post()
                if tx.invoice_ids:
                    (tx.payment_id.move_id.line_ids + tx.invoice_ids.line_ids).filtered(
                        lambda line: line.account_id == tx.payment_id.destination_account_id and not line.reconciled
                    ).reconcile()
