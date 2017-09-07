# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, fields, api, _
from openerp.exceptions import ValidationError
from ast import literal_eval


class AccountPayment(models.Model):
    _inherit = "account.payment"

    payment_group_id = fields.Many2one(
        'account.payment.group',
        'Payment Group',
        ondelete='cascade',
        readonly=True,
    )
    # we add this field so company can be send in context when adding payments
    # before payment group is saved
    payment_group_company_id = fields.Many2one(
        related='payment_group_id.company_id', readonly=True,)
    # we make a copy without transfer option, we try with related but it
    # does not works
    payment_type_copy = fields.Selection(
        selection=[('outbound', 'Send Money'), ('inbound', 'Receive Money')],
        compute='_compute_payment_type_copy',
        inverse='_inverse_payment_type_copy',
        string='Payment Type'
    )
    amount_company_currency = fields.Monetary(
        string='Payment Amount on Company Currency',
        compute='_compute_amount_company_currency',
        currency_field='company_currency_id',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id'
    )

    @api.multi
    @api.depends('amount', 'currency_id', 'company_id.currency_id')
    def _compute_amount_company_currency(self):
        for rec in self:
            payment_currency = rec.currency_id
            company_currency = rec.company_id.currency_id
            if payment_currency and payment_currency != company_currency:
                amount_company_currency = rec.currency_id.with_context(
                    date=rec.payment_date).compute(
                        rec.amount, rec.company_id.currency_id)
            else:
                amount_company_currency = rec.amount
            sign = 1.0
            if (
                    (rec.partner_type == 'supplier' and
                        rec.payment_type == rec.payment_type == 'inbound') or
                    (rec.partner_type == 'customer' and
                        rec.payment_type == rec.payment_type == 'outbound')):
                sign = -1.0
            rec.amount_company_currency = amount_company_currency * sign

    @api.multi
    @api.onchange('payment_type_copy')
    def _inverse_payment_type_copy(self):
        for rec in self:
            # if false, then it is a transfer
            rec.payment_type = (
                rec.payment_type_copy and rec.payment_type_copy or 'transfer')

    @api.multi
    @api.depends('payment_type')
    def _compute_payment_type_copy(self):
        for rec in self:
            if rec.payment_type == 'transfer':
                continue
            rec.payment_type_copy = rec.payment_type

    @api.multi
    def get_journals_domain(self):
        domain = super(AccountPayment, self).get_journals_domain()
        if self.payment_group_company_id:
            domain.append(
                ('company_id', '=', self.payment_group_company_id.id))
        return domain

    @api.multi
    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        """
        we disable change of partner_type if we came from a payment_group
        """
        if not self._context.get('payment_group'):
            return super(AccountPayment, self)._onchange_payment_type()

    @api.multi
    @api.constrains('payment_group_id', 'payment_type')
    def check_payment_group(self):
        # TODO check this
        # we add this key mainly for odoo test that are gives error because no
        # payment group for those test cases, we should fix it in another way
        # but perhups we use this parameter to allow this payments in some
        # cases
        if literal_eval(self.env['ir.config_parameter'].get_param(
                'enable_payments_without_payment_group', 'False')):
            return True
        for rec in self:
            if rec.payment_type == 'transfer':
                if rec.payment_group_id:
                    raise ValidationError(_(
                        'Payments must be created from payments groups'))
            else:
                if not rec.payment_group_id:
                    raise ValidationError(_(
                        'Payments must be created from payments groups'))

    @api.multi
    @api.depends('invoice_ids', 'payment_type', 'partner_type', 'partner_id')
    def _compute_destination_account_id(self):
        """
        If we are paying a payment gorup with paylines, we use account
        of lines that are going to be paid
        """
        for rec in self:
            to_pay_account = rec.payment_group_id.to_pay_move_line_ids.mapped(
                'account_id')
            if len(to_pay_account) > 1:
                raise ValidationError(_(
                    'To Pay Lines must be of the same account!'))
            elif len(to_pay_account) == 1:
                rec.destination_account_id = to_pay_account[0]
            else:
                super(AccountPayment, rec)._compute_destination_account_id()

    @api.multi
    def show_details(self):
        """
        Metodo para mostrar form editable de payment, principalmente para ser
        usado cuando hacemos ajustes y el payment group esta confirmado pero
        queremos editar una linea
        """
        return {
            'name': _('Payment Lines'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment',
            'target': 'new',
            'res_id': self.id,
            'context': self._context,
        }
