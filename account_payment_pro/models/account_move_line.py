from odoo import models, fields, api, _
from odoo.exceptions import UserError


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

    def action_register_payment(self):

        if self._use_default_payment_register():
            return super().action_register_payment()

        to_pay_move_lines = self.filtered(
                lambda r: not r.reconciled and r.account_id.account_type in ['asset_receivable', 'liability_payable'])
        if not to_pay_move_lines:
            raise UserError(_('Nothing to be paid on selected entries'))
        to_pay_partners = self.mapped('move_id.commercial_partner_id')
        if len(to_pay_partners) > 1:
            raise UserError(_('Selected recrods must be of the same partner'))
        partner_type = 'customer' if to_pay_move_lines[0].account_id.account_type == 'asset_receivable' else 'supplier'
        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'context': {
                'active_model': 'account.move.line',
                'active_ids': self.ids,
                'default_payment_type': 'inbound' if partner_type == 'customer' else 'outbound',
                'default_partner_type': partner_type,
                'default_partner_id': to_pay_partners.id,
                'default_to_pay_move_line_ids': to_pay_move_lines.ids,
                # We set this because if became from other view and in the context has 'create=False'
                # you can't crate payment lines (for ej: subscription)
                'create': True,
                'default_company_id': self.company_id.id,
                'pop_up': True,
            },
            'target': 'current',
            'type': 'ir.actions.act_window',
        }

    def _use_default_payment_register(self):
        return False
