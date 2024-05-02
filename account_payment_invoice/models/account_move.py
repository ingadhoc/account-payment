##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.tools import plaintext2html


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
        for rec in self.filtered(lambda x: x.payment_state=='not_paid' and {'pending','authorized'}.intersection(set(x.transaction_ids.mapped('state')))):
            rec.payment_state = 'electronic_pending'

    def action_post(self):
        res = super().action_post()
        to_pay_moves = self.filtered(
                lambda x: x.payment_token_id and x.state == 'posted' and
                x.payment_state in ['not_paid', 'electronic_pending'] and x.move_type == 'out_invoice')
        to_pay_moves.sudo().create_electronic_payment()
        return res

    def create_electronic_payment(self):
        tx_obj = self.env['payment.transaction']
        for rec in self:
            active_transaction_amount = sum(rec.transaction_ids.filtered(lambda tx: tx.state in ['authorized', 'done','pending']).mapped('amount'))
            if rec.currency_id.compare_amounts(rec.amount_total, active_transaction_amount) > 0.0:
                try:
                    transaction = tx_obj.create({
                                                'provider_id': rec.payment_token_id.provider_id.id,
                                                'amount': rec.amount_total - active_transaction_amount,
                                                'currency_id': rec.currency_id.id,
                                                'partner_id': rec.partner_id.id,
                                                'token_id': rec.payment_token_id.id,
                                                'operation': 'offline',
                                                'invoice_ids': [(6, 0, [rec.id])],
                                            })
                    transaction._send_payment_request()
                    transaction._cr.commit()
                except Exception as exp:
                    rec.message_post(
                        body=_('We tried to validate this payment but got this error') + ': \n\n' + plaintext2html(str(exp), 'em'),
                        partner_ids=rec.get_internal_partners().ids,
                        body_is_html=True)
