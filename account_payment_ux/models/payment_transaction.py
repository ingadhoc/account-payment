from odoo import models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _reconcile_after_done(self):
        super()._reconcile_after_done()

        # Si el pago relacionado a la trasaccion esta en draft y coinciden los datos
        # lo publico y concilio
        if self.state == 'done' and self.payment_id and self.payment_id.state == 'draft' and \
            self.payment_id.currency_id == self.currency_id and \
            self.payment_id.amount == abs(self.amount):

            self.payment_id.action_post()
            if self.invoice_ids:
                self.invoice_ids.filtered(lambda inv: inv.state == 'draft').action_post()

                (self.payment_id.line_ids + self.invoice_ids.line_ids).filtered(
                    lambda line: line.account_id == self.payment_id.destination_account_id
                    and not line.reconciled
                ).reconcile()

    def write(self, vals):
        # Este hack es para evitar que las transacciones se marquen como post processed = True
        # Cuando las genero pendientes desde el back end
        # 1) Llama a _finalize_post_processing
        # https://github.com/odoo/odoo/blob/16.0/addons/account_payment/models/account_payment.py#L143
        # 2) _finalize_post_processing siempre marca la transaccion como is_post_processed
        # aunque su estado no sea DONE...
        # https://github.com/odoo/odoo/blob/16.0/addons/payment/models/payment_transaction.py#L890

        ignoned_post_processed_tx = self.env['payment.transaction']
        if vals.get('is_post_processed') and vals.get('state', 'draft') in ['draft', 'pending']:
            altered_vals = vals.copy()
            del altered_vals['is_post_processed']
            ignoned_post_processed_tx = self.filtered(lambda x: x.state in ['draft', 'pending'])
            ignoned_post_processed_tx.write(altered_vals)
        return super(PaymentTransaction, self - ignoned_post_processed_tx).write(vals)
