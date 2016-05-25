# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning


class account_voucher(models.Model):
    _inherit = "account.voucher"

    company_double_validation = fields.Boolean(
        related='company_id.double_validation',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', _('Draft')),
            ('confirmed', _('Confirmed')),
            ('cancel', _('Cancelled')),
            ('proforma', _('Pro-forma')),
            ('posted', _('Posted'))
        ])
    # we need amount to be not readonly on confirmed in order to compute the
    # value
    amount = fields.Float(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    account_id = fields.Many2one(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    net_amount = fields.Float(
        required=False,
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    # no funciono bien
    # net_amount_copy = fields.Float(
    #     related='net_amount',
    #     states={
    #         'confirmed': [('readonly', False)]}
    #     )
    journal_id = fields.Many2one(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    received_third_check_ids = fields.One2many(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    issued_check_ids = fields.One2many(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    delivered_third_check_ids = fields.One2many(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    withholding_ids = fields.One2many(
        states={'draft': [('readonly', False)],
                'confirmed': [('readonly', False)]}
    )
    date = fields.Date(
        default=False,
    )
    payment_date = fields.Date(
        string='Payment Date',
        readonly=True,
        states={'draft': [('readonly', False)]},
        help='Payment can not be validated before this date',
    )
    to_pay_amount = fields.Float(
        'Importe a Pagar',
        # _('To Pay Amount'),
        # waiting for a PR 9081 to fix computed fields translations
        help='Importe a ser pagado',
        # help=_('Amount To be Paid'),
        compute='_get_to_pay_amount',
        digits=dp.get_precision('Account'),
    )
    difference_amount = fields.Float(
        compute='_get_to_pay_amount',
        help='Diferencia enre el importe a ser pagado y el importe pagado',
        digits=dp.get_precision('Account'),
    )
    advance_amount = fields.Float(
        'Advance Amount',
        digits=dp.get_precision('Account'),
        readonly=True,
        states={'draft': [('readonly', False)]},
        help='Amount to be advance and not conciliated with debts',
    )
    confirmation_date = fields.Date(
        'Fecha de Confirmación',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False,
    )

    @api.one
    @api.depends('writeoff_amount', 'advance_amount')
    def _get_to_pay_amount(self):
        """
        On v8 it is only updated on save.
        In v9 should be updated live
        """
        # Can not use this way because old api
        debit = sum([x.amount for x in self.line_cr_ids])
        credit = sum([x.amount for x in self.line_dr_ids])
        # TODO probablemente haya que multiplicar por sign dependiendo receipt
        # o payment
        to_pay_amount = credit - debit + self.advance_amount
        self.to_pay_amount = to_pay_amount
        self.difference_amount = to_pay_amount - self.amount

    @api.multi
    def action_confirm(self):
        for voucher in self:
            if not voucher.confirmation_date:
                voucher.write({
                    'state': 'confirmed',
                    'confirmation_date': fields.Datetime.now()
                })
            else:
                voucher.write({
                    'state': 'confirmed',
                })

    @api.multi
    def proforma_voucher(self):
        """Make two things:
        * Check payment date valididy
        * Fix not date on voucher error, set actual date.
        """
        for voucher in self:
            if not voucher.date:
                voucher.date = fields.Date.context_today(self)
            # only check payments for now
            if (
                    voucher.type != 'payment' or
                    not voucher.company_double_validation
            ):
                continue
            if (
                    voucher.currency_id.round(
                        voucher.amount - voucher.to_pay_amount) and
                    not voucher.journal_id.allow_validation_difference):
                raise Warning(_(
                    'You can not validate a Voucher that has '
                    'Total Amount different from To Pay Amount'))
            if voucher.payment_date > fields.Date.context_today(self):
                raise Warning(_(
                    'You can not validate a Voucher that has '
                    'Payment Date before Today'))
        return super(account_voucher, self).proforma_voucher()

    @api.onchange('currency_id')
    def currency_change_check(self):
        if self.state == 'confirmed':
            return {'warning': {
                'title': _('Warning!'),
                'message': _(
                    'You can not change to a journal of other currency on '
                    'confirmed state, you should return to draft state')}}

    def onchange_amount(
            self, cr, uid, ids, amount, rate, partner_id, journal_id,
            currency_id, ttype, date, payment_rate_currency_id, company_id,
            context=None):
        res = super(account_voucher, self).onchange_amount(
            cr, uid, ids, amount, rate, partner_id, journal_id,
            currency_id, ttype, date, payment_rate_currency_id, company_id,
            context=context)
        for voucher in self.browse(cr, uid, ids, context=context):
            # if confirmed we clean voucher lines
            if res.get('value') and voucher.state == 'confirmed':
                if res['value'].get('line_cr_ids'):
                    del res['value']['line_cr_ids']
                if res['value'].get('line_dr_ids'):
                    del res['value']['line_dr_ids']
        return res

    def onchange_journal(self, cr, uid, ids, journal_id, line_ids, tax_id,
                         partner_id, date, amount, ttype, company_id,
                         context=None):
        res = super(account_voucher, self).onchange_journal(
            cr, uid, ids, journal_id, line_ids, tax_id, partner_id, date,
            amount, ttype, company_id, context=context)
        if not res:
            res = {}
        for voucher in self.browse(cr, uid, ids, context=context):
            # if confirmed we clean voucher lines
            if res.get('value') and voucher.state == 'confirmed':
                if res['value'].get('line_cr_ids'):
                    del res['value']['line_cr_ids']
                if res['value'].get('line_dr_ids'):
                    del res['value']['line_dr_ids']
        return res
