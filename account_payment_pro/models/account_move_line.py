from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    payment_matched_amount = fields.Monetary(
        compute='_compute_payment_matched_amount',
        currency_field='company_currency_id',
    )

    @api.depends_context('matched_payment_ids')
    def _compute_payment_matched_amount(self):
        """
        Reciviendo un matched_payment_id por contexto, decimos en ese payment, cuanto se pago para la lína en cuestión.
        """
        matched_payment_ids = self._context.get('matched_payment_ids')

        if not matched_payment_ids:
            self.payment_matched_amount = 0.0
            return False
        payments = self.env['account.payment'].search([('id', 'in', matched_payment_ids)])
        payment_lines = payments.mapped('line_ids').filtered(lambda x: x.account_type in ['asset_receivable', 'liability_payable'])
        for rec in self:
            debit_move_amount = sum(payment_lines.mapped('matched_debit_ids').filtered(lambda x: x.debit_move_id == rec).mapped('amount'))
            credit_move_amount = sum(payment_lines.mapped('matched_credit_ids').filtered(lambda x: x.credit_move_id == rec).mapped('amount'))
            rec.payment_matched_amount = debit_move_amount - credit_move_amount

    def action_register_payment(self):
        to_pay_partners = self.mapped('move_id.commercial_partner_id') or self.mapped('partner_id')
        company_pay_pro = len(self.mapped('company_id').ids) == 1 and self.mapped('company_id').use_payment_pro
        payment_pro = self._context.get('force_payment_pro')
        # si force_payment_pro se pasa como False estamos forzando no usar payment pro, vamos a metodo original
        # usamos payment pro si lo pasamos forzado (Caso pay and new donde todavia no tenemos company) o si estoy
        # pagando deuda de una sola cia y tiene payment pro
        # y si ademas estoy pagando solo deuda de un partner
        if payment_pro is not False and ((payment_pro or company_pay_pro) and len(to_pay_partners) <= 1):
            to_pay_move_lines = self.filtered(
                    lambda r: not r.reconciled and r.account_id.account_type in ['asset_receivable', 'liability_payable'])
            if not to_pay_move_lines:
                partner_type = self._context.get('default_partner_type')
                to_pay_partner_id = self._context.get('default_partner_id')
                company_id = self._context.get('default_company_id')
                if not partner_type or not to_pay_partner_id:
                    raise UserError(_('Nothing to be paid on selected entries'))
            else:
                to_pay_partner_id = to_pay_partners.id
                partner_type = 'customer' if to_pay_move_lines[0].account_id.account_type == 'asset_receivable' else 'supplier'
                company_id = self.company_id.id
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
                    'default_partner_id': to_pay_partner_id,
                    'default_to_pay_move_line_ids': to_pay_move_lines.ids,
                    # We set this because if became from other view and in the context has 'create=False'
                    # you can't crate payment lines (for ej: subscription)
                    'create': True,
                    'default_to_pay_amount': abs(sum(line.amount_residual for line in to_pay_move_lines)),
                    'default_company_id': company_id,
                },
                'target': 'current',
                'type': 'ir.actions.act_window',
            }
        else:
            return super().action_register_payment()
