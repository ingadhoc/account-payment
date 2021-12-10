# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

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
        # use copy false for two reasons:
        # 1. when making refund it's safer to make pay now empty (specially if automatic refund validation is enable)
        # 2. on duplicating an invoice it's safer also
        copy=False,
    )
    payment_group_ids = fields.Many2many(
        'account.payment.group',
        compute='_compute_payment_groups',
        string='Payment Groups',
        compute_sudo=True,
    )

    def _compute_payment_groups(self):
        """
        El campo en invoices "payment_id" no lo seteamos con los payment groups
        Por eso tenemos que calcular este campo
        """
        for rec in self:
            rec.payment_group_ids = rec._get_reconciled_payments().mapped('payment_group_id')

    def _get_tax_factor(self):
        self.ensure_one()
        return (self.amount_total and (
            self.amount_untaxed / self.amount_total) or 1.0)

    @api.depends('line_ids.account_id.internal_type', 'line_ids.reconciled')
    def _compute_open_move_lines(self):
        for rec in self:
            rec.open_move_line_ids = rec.line_ids.filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

    def action_account_invoice_payment_group(self):
        self.ensure_one()
        if self.state == 'cancel' or self.invoice_payment_state != 'not_paid':
            raise ValidationError(_('You can only register payment if invoice is not cancelled and unpaid'))
        return {
            'name': _('Register Payment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment.group',
            'view_id': False,
            'target': 'current',
            'type': 'ir.actions.act_window',
            'context': {
                # si bien el partner se puede adivinar desde los apuntes
                # con el default de payment group, preferimos mandar por aca
                # ya que puede ser un contacto y no el commercial partner (y
                # en los apuntes solo hay commercial partner)
                'default_partner_id': self.partner_id.id,
                'to_pay_move_line_ids': self.open_move_line_ids.ids,
                'pop_up': True,
                # We set this because if became from other view and in the
                # context has 'create=False' you can't crate payment lines
                #  (for ej: subscription)
                'create': True,
                'default_company_id': self.company_id.id,
            },
        }

    def action_post(self):
        res = super(AccountMove, self).action_post()
        self.pay_now()
        return res

    def pay_now(self):
        # validate_payment = not self._context.get('validate_payment')
        for rec in self:
            pay_journal = rec.pay_now_journal_id
            if pay_journal and rec.state == 'posted' and rec.invoice_payment_state == 'not_paid':
                # si bien no hace falta mandar el partner_type al paygroup
                # porque el defaults lo calcula solo en funcion al tipo de
                # cuenta, es mas claro mandarlo y podria evitar error si
                # estamos usando cuentas cruzadas (payable, receivable) con
                # tipo de factura
                if rec.type in ['in_invoice', 'in_refund']:
                    partner_type = 'supplier'
                else:
                    partner_type = 'customer'

                pay_context = {
                    'to_pay_move_line_ids': (rec.open_move_line_ids.ids),
                    'default_company_id': rec.company_id.id,
                    'default_partner_type': partner_type,
                }

                payment_group = rec.env[
                    'account.payment.group'].with_context(
                        pay_context).create({
                            'payment_date': rec.invoice_date
                        })
                # el difference es positivo para facturas (de cliente o
                # proveedor) pero negativo para NC.
                # para factura de proveedor o NC de cliente es outbound
                # para factura de cliente o NC de proveedor es inbound
                # igualmente lo hacemos con el difference y no con el type
                # por las dudas de que facturas en negativo
                if (
                        partner_type == 'supplier' and
                        payment_group.payment_difference >= 0.0 or
                        partner_type == 'customer' and
                        payment_group.payment_difference < 0.0):
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

                payment_group.payment_ids.create({
                    'payment_group_id': payment_group.id,
                    'payment_type': payment_type,
                    'partner_type': partner_type,
                    'company_id': rec.company_id.id,
                    'partner_id': payment_group.partner_id.id,
                    'amount': abs(payment_group.payment_difference),
                    'journal_id': pay_journal.id,
                    'payment_method_id': payment_method.id,
                    'payment_date': rec.invoice_date,
                })
                # if validate_payment:
                payment_group.post()

    def action_view_payment_groups(self):
        if self.type in ('in_invoice', 'in_refund'):
            action = self.env.ref(
                'account_payment_group.action_account_payments_group_payable')
        else:
            action = self.env.ref(
                'account_payment_group.action_account_payments_group')

        result = action.read()[0]

        if len(self.payment_group_ids) != 1:
            result['domain'] = [('id', 'in', self.payment_group_ids.ids)]
        elif len(self.payment_group_ids) == 1:
            res = self.env.ref(
                'account_payment_group.view_account_payment_group_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = self.payment_group_ids.id
        return result

    @api.onchange('journal_id')
    def _onchange_journal_reset_pay_now(self):
        # while not always it should be reseted (only if changing company) it's not so usual to set pay now first
        # and then change journal
        self.pay_now_journal_id = False

    def button_draft(self):
        self.filtered(lambda x: x.state == 'posted' and x.pay_now_journal_id).write({'pay_now_journal_id': False})
        return super().button_draft()
