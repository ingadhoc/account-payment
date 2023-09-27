##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class AccountMove(models.Model):

    _inherit = "account.move"
    payment_state = fields.Selection(
        selection_add=[('electronic_pending', 'Electronic payment')],
        ondelete={'electronic_pending': 'cascade'}
    )
    payment_token_id = fields.Many2one('payment.token', string="automatic electonic payment",
                        check_company=True, readonly=True, states={'draft': [('readonly', False)]}, copy=False)

    @api.depends('transaction_ids.state')
    def _compute_payment_state(self):
        super()._compute_payment_state()
        for rec in self.filtered(lambda x: x.payment_state=='not_paid' and {'done','pending','authorized'}.intersection(set(x.transaction_ids.mapped('state')))):
            rec.payment_state = 'electronic_pending'

    def _post(self, soft=True):
        res = super()._post(soft=soft)
        to_pay_moves = self.filtered(
                lambda x: x.payment_token_id and x.state == 'posted' and
                x.payment_state in ['not_paid', 'electronic_pending'] and x.move_type == 'out_invoice')
        to_pay_moves.create_electronic_payment()
        return res

    def create_electronic_payment(self):
        tx_obj = self.env['payment.transaction']
        values = []
        for rec in self:
            active_transaction_amount = sum(rec.transaction_ids.filtered(lambda tx: tx.state in ['authorized', 'done','pending']).mapped('amount'))
            if rec.currency_id.compare_amounts(rec.amount_total, active_transaction_amount) > 0.0:
                values.append({
                    'provider_id': rec.payment_token_id.provider_id.id,
                    'amount': rec.amount_total - active_transaction_amount,
                    'currency_id': rec.currency_id.id,
                    'partner_id': rec.partner_id.id,
                    'token_id': rec.payment_token_id.id,
                    'operation': 'offline',
                    'invoice_ids': [(6, 0, [rec.id])],
                })
        transactions = tx_obj.create(values)
        for tx in transactions:
            tx._send_payment_request()
