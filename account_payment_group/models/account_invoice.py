# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import ValidationError


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    open_move_line_ids = fields.One2many(
        'account.move.line',
        compute='_compute_open_move_lines'
    )
    pay_now_journal_id = fields.Many2one(
        'account.journal',
        'Pay now Journal',
        help='If you set a journal here, after invoice validation, the invoice'
        ' will be automatically paid with this journal. As manual payment'
        'method is used, only journals with manual method are shown.',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )

    @api.multi
    def _get_tax_factor(self):
        self.ensure_one()
        return (self.amount_total and (
            self.amount_untaxed / self.amount_total) or 1.0)

    @api.multi
    def _compute_open_move_lines(self):
        for rec in self:
            rec.open_move_line_ids = rec.move_id.line_ids.filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

    @api.multi
    def action_account_invoice_payment_group(self):
        self.ensure_one()
        if self.state != 'open':
            raise ValidationError(_(
                'You can only register payment if invoice is open'))
        # target = 'new'
        # if self.company_id.double_validation:
        #     target = 'current'
        return {
            'name': _('Register Payment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment.group',
            'view_id': False,
            'target': 'current',
            # 'target': target,
            'type': 'ir.actions.act_window',
            # 'domain': [('id', 'in', aml.ids)],
            'context': {
                'to_pay_move_line_ids': self.open_move_line_ids.ids,
                'pop_up': True,
                'default_company_id': self.company_id.id,
            },
        }

    @api.multi
    def invoice_validate(self):
        res = super(AccountInvoice, self).invoice_validate()
        self.pay_now()
        return res

    @api.multi
    def pay_now(self):
        # validate_payment = not self._context.get('validate_payment')
        for rec in self:
            pay_journal = rec.pay_now_journal_id
            if pay_journal and rec.state == 'open':
                pay_context = {
                    'to_pay_move_line_ids': (rec.open_move_line_ids.ids),
                    'default_company_id': rec.company_id.id,
                }
                # factura de proveedor o reembolso a cliente, es saliente
                if rec.type in ['in_invoice', 'out_refund']:
                    payment_type = 'outbound'
                    payment_methods = pay_journal.outbound_payment_method_ids
                else:
                    payment_type = 'inbound'
                    payment_methods = pay_journal.inbound_payment_method_ids

                payment_method = payment_methods.filtered(
                    lambda x: x.code == 'manual')
                if not payment_method:
                    raise ValidationError(_(
                        'Pay now journal must have manual method!'))

                if rec.type in ['in_invoice', 'in_refund']:
                    partner_type = 'supplier'
                else:
                    partner_type = 'customer'

                payment_group = rec.env[
                    'account.payment.group'].with_context(
                        pay_context).create({})
                payment_group.payment_ids.create({
                    'payment_group_id': payment_group.id,
                    'payment_type': payment_type,
                    'partner_type': partner_type,
                    'company_id': rec.company_id.id,
                    'partner_id': payment_group.partner_id.id,
                    'amount': payment_group.payment_difference,
                    'journal_id': pay_journal.id,
                    'payment_method_id': payment_method.id,
                })
                # if validate_payment:
                payment_group.post()
