from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        """ Odoo a partir de 16, cuando se valida un pago con token, si la transaccion no queda en done cancela el pago
        por ahora nosotros revertimos este cambio para el caso de tu cuota"""
        return super(AccountPayment, self.with_context(from_action_post=True)).action_post()

    def action_cancel(self):
        if self._context.get('from_action_post'):
            self = self - self.filtered(lambda x: x.payment_transaction_id.state in ['draft', 'pending', 'authorized'])
        return super(AccountPayment, self).action_cancel()
