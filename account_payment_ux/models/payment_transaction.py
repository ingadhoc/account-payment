from odoo import models 


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _reconcile_after_done(self):
        super()._reconcile_after_done()    

        # Si el pago relacionado a la trasaccion esta en draft y coinciden los datos
        # lo publico y concilio 
        if self.payment_id and self.payment_id.state == 'draft' and \
            self.payment_id.currency_id == self.currency_id and \
            self.payment_id.amount == abs(self.amount):
            
            self.payment_id.action_post()
            if self.invoice_ids:
                self.invoice_ids.filtered(lambda inv: inv.state == 'draft').action_post()

                (self.payment_id.line_ids + self.invoice_ids.line_ids).filtered(
                    lambda line: line.account_id == self.payment_id.destination_account_id
                    and not line.reconciled
                ).reconcile()
