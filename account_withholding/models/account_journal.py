from odoo import models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _default_outbound_payment_methods(self):
        if self._context.get('withholding_journal'):
            return self.env.ref('account_withholding.account_payment_method_out_withholding')
        return super()._default_outbound_payment_methods()

    def _default_inbound_payment_methods(self):
        if self._context.get('withholding_journal'):
            return self.env.ref('account_withholding.account_payment_method_in_withholding')
        return super()._default_inbound_payment_methods()
