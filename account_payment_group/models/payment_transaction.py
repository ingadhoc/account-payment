##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import api, models


class PaymentTransaction(models.Model):

    _inherit = 'payment.transaction'

    @api.multi
    def _reconcile_after_transaction_done(self):
        return super(PaymentTransaction, self.with_context(
            create_from_website=True))._reconcile_after_transaction_done()
