from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    payment_matched_amount = fields.Monetary(
        compute='_compute_payment_matched_amount',
        currency_field='company_currency_id',
    )

    @api.depends_context('matched_payment_id')
    def _compute_payment_matched_amount(self):
        """
        Reciviendo un matched_payment_id por contexto, decimos en ese payment, cuanto se pago para la lína en cuestión.
        """
        matched_payment_id = self._context.get('matched_payment_id', self._context.get('params', {}).get('id'))

        if not matched_payment_id:
            self.payment_matched_amount = 0.0
            return False
        payments = self.env['account.payment'].browse(matched_payment_id)
        payment_lines = payments.line_ids.filtered(lambda x: x.account_type in ['asset_receivable', 'liability_payable'])
        for rec in self:
            debit_move_amount = sum(payment_lines.mapped('matched_debit_ids').filtered(lambda x: x.debit_move_id == rec).mapped('amount'))
            credit_move_amount = sum(payment_lines.mapped('matched_credit_ids').filtered(lambda x: x.credit_move_id == rec).mapped('amount'))
            rec.payment_matched_amount = debit_move_amount - credit_move_amount
