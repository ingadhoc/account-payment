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
                    (tx.payment_id.line_ids + tx.invoice_ids.line_ids).filtered(
                        lambda line: line.account_id == tx.payment_id.destination_account_id and not line.reconciled
                    ).reconcile()

    def write(self, vals):
        # Este hack es para evitar que las transacciones se marquen como post processed = True
        # Cuando las genero pendientes desde el back end
        # 1) Llama a _post_process
        # https://github.com/odoo/odoo/blob/18.0/addons/account_payment/models/account_payment.py#L141C22-L141C35
        # 2) _finalize_post_processing siempre marca la transaccion como _post_process
        # aunque su estado no sea DONE...
        # https://github.com/odoo/odoo/blob/18.0/addons/payment/models/payment_transaction.py#L873
        ignoned_post_processed_tx = self.env["payment.transaction"]
        if vals.get("is_post_processed") and vals.get("state", "draft") in ["draft", "pending"]:
            altered_vals = vals.copy()
            del altered_vals["is_post_processed"]
            ignoned_post_processed_tx = self.filtered(
                lambda x: x.state in ["draft", "pending"] and x.provider_id.code != "custom"
            )
            ignoned_post_processed_tx.write(altered_vals)
        return super(PaymentTransaction, self - ignoned_post_processed_tx).write(vals)
