# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from ast import literal_eval
import logging
_logger = logging.getLogger(__name__)


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
    signed_amount = fields.Monetary(
        string='Payment Amount',
        compute='_compute_signed_amount',
    )
    signed_amount_company_currency = fields.Monetary(
        string='Payment Amount on Company Currency',
        compute='_compute_signed_amount',
        currency_field='company_currency_id',
    )
    amount_company_currency = fields.Monetary(
        string='Payment Amount on Company Currency',
        compute='_compute_amount_company_currency',
        inverse='_inverse_amount_company_currency',
        currency_field='company_currency_id',
    )
    other_currency = fields.Boolean(
        compute='_compute_other_currency',
    )
    force_amount_company_currency = fields.Monetary(
        string='Payment Amount on Company Currency',
        currency_field='company_currency_id',
        copy=False,
    )
    exchange_rate = fields.Float(
        string='Exchange Rate',
        compute='_compute_exchange_rate',
        # readonly=False,
        # inverse='_inverse_exchange_rate',
        digits=(16, 4),
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
    )

    @api.multi
    @api.depends(
        'amount', 'payment_type', 'partner_type', 'amount_company_currency')
    def _compute_signed_amount(self):
        for rec in self:
            sign = 1.0
            if (
                    (rec.partner_type == 'supplier' and
                        rec.payment_type == 'inbound') or
                    (rec.partner_type == 'customer' and
                        rec.payment_type == 'outbound')):
                sign = -1.0
            rec.signed_amount = rec.amount and rec.amount * sign
            rec.signed_amount_company_currency = (
                rec.amount_company_currency and
                rec.amount_company_currency * sign)

    @api.multi
    @api.depends('currency_id', 'company_currency_id')
    def _compute_other_currency(self):
        for rec in self:
            if rec.company_currency_id and rec.currency_id and \
                    rec.company_currency_id != rec.currency_id:
                rec.other_currency = True

    @api.multi
    @api.depends(
        'amount', 'other_currency', 'amount_company_currency')
    def _compute_exchange_rate(self):
        for rec in self.filtered('other_currency'):
            rec.exchange_rate = rec.amount and (
                rec.amount_company_currency / rec.amount) or 0.0

    @api.multi
    # this onchange is necesary because odoo, sometimes, re-compute
    # and overwrites amount_company_currency. That happends due to an issue
    # with rounding of amount field (amount field is not change but due to
    # rouding odoo believes amount has changed)
    @api.onchange('amount_company_currency')
    def _inverse_amount_company_currency(self):
        _logger.info('Running inverse amount company currency')
        for rec in self:
            if rec.other_currency and rec.amount_company_currency != \
                    rec.currency_id.with_context(
                        date=rec.payment_date).compute(
                        rec.amount, rec.company_id.currency_id):
                force_amount_company_currency = rec.amount_company_currency
            else:
                force_amount_company_currency = False
            rec.force_amount_company_currency = force_amount_company_currency

    @api.multi
    @api.depends('amount', 'other_currency', 'force_amount_company_currency')
    def _compute_amount_company_currency(self):
        """
        * Si las monedas son iguales devuelve 1
        * si no, si hay force_amount_company_currency, devuelve ese valor
        * sino, devuelve el amount convertido a la moneda de la cia
        """
        _logger.info('Computing amount company currency')
        for rec in self:
            if not rec.other_currency:
                amount_company_currency = rec.amount
            elif rec.force_amount_company_currency:
                amount_company_currency = rec.force_amount_company_currency
            else:
                amount_company_currency = rec.currency_id.with_context(
                    date=rec.payment_date).compute(
                        rec.amount, rec.company_id.currency_id)
            rec.amount_company_currency = amount_company_currency

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
        if literal_eval(self.env['ir.config_parameter'].sudo().get_param(
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

    def _get_shared_move_line_vals(
            self, debit, credit, amount_currency, move_id, invoice_id=False):
        """
        Si se esta forzando importe en moneda de cia, usamos este importe
        para debito/credito
        """
        res = super(AccountPayment, self)._get_shared_move_line_vals(
            debit, credit, amount_currency, move_id, invoice_id=invoice_id)
        if self.force_amount_company_currency:
            if res.get('debit', False):
                res['debit'] = self.force_amount_company_currency
            if res.get('credit', False):
                res['credit'] = self.force_amount_company_currency
        return res

    def _get_move_vals(self, journal=None):
        """If we have a communication on payment group append it before
        payment communication
        """
        vals = super(AccountPayment, self)._get_move_vals(journal=journal)
        if self.payment_group_id.communication:
            vals['ref'] = "%s%s" % (
                self.payment_group_id.communication,
                self.communication and ": %s" % self.communication or "")
        return vals
