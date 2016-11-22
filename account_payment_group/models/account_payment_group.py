# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import UserError, ValidationError


MAP_PARTNER_TYPE_ACCOUNT_TYPE = {
    'customer': 'receivable',
    'supplier': 'payable',
}
MAP_ACCOUNT_TYPE_PARTNER_TYPE = {
    'receivable': 'customer',
    'payable': 'supplier',
}


class AccountPaymentGroup(models.Model):
    _name = "account.payment.group"
    _description = "Payment Group"
    _order = "payment_date desc"

    # campos copiados de payment
    # payment_type = fields.Selection(
    #     [('outbound', 'Send Money'), ('inbound', 'Receive Money')],
    #     string='Payment Type',
    #     required=True,
    #     readonly=True,
    #     states={'draft': [('readonly', False)]},
    # )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.user.company_id,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    partner_type = fields.Selection(
        [('customer', 'Customer'), ('supplier', 'Vendor')]
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    commercial_partner_id = fields.Many2one(
        related='partner_id.commercial_partner_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.user.company_id.currency_id,
    )
    payment_date = fields.Date(
        string='Payment Date',
        default=fields.Date.context_today,
        required=True,
        copy=False
    )
    communication = fields.Char(
        string='Memo'
    )
    notes = fields.Text(
        string='Notes'
    )

    # campos nuevos
    # reconcile = fields.Selection([
    #     ('invoices', 'Invoices'),
    #     ('move_lines', 'Entry Lines')],
    #     required=True,
    #     default='move_lines',
    #     # default='invoices',
    # )
    # rename fields or labels
    matched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
    )
    unmatched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
    )

    @api.multi
    @api.depends(
        'state',
        'payments_amount',
        'matched_move_line_ids.payment_group_matched_amount')
    def _compute_matched_amounts(self):
        for rec in self:
            if rec.state != 'posted':
                continue
            rec.matched_amount = sum(rec.matched_move_line_ids.with_context(
                payment_group_id=rec.id).mapped(
                    'payment_group_matched_amount'))
            rec.unmatched_amount = rec.payments_amount - rec.matched_amount

    selected_debt = fields.Monetary(
        readonly=True,
        # string='To Pay lines Amount',
        string='Selected Debt',
    )
    unreconciled_amount = fields.Monetary(
        string='Adjusment / Advance',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    # reconciled_amount = fields.Monetary(compute='_compute_amounts')
    to_pay_amount = fields.Monetary(
        compute='_compute_to_pay_amount',
        inverse='_inverse_to_pay_amount',
        string='To Pay Amount',
        # string='Total To Pay Amount',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )

    payments_amount = fields.Monetary(
        compute='_compute_payments_amount',
        string='Amount',
    )
    # name = fields.Char(
    #     readonly=True,
    #     copy=False,
    #     default="Draft Payment"
    # )   # The name is attributed upon post()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('posted', 'Posted'),
        # ('sent', 'Sent'),
        # ('reconciled', 'Reconciled')
    ], readonly=True, default='draft', copy=False, string="Status"
    )
    move_lines_domain = (
        "["
        "('partner_id.commercial_partner_id', '=', commercial_partner_id),"
        "('account_id.internal_type', '=', account_internal_type),"
        "('account_id.reconcile', '=', True),"
        "('reconciled', '=', False),"
        # '|',
        # ('amount_residual', '!=', False),
        # ('amount_residual_currency', '!=', False),
        "]")
    debt_move_line_ids = fields.Many2many(
        # 'account.move.line',
        # 'account_move_line_payment_group_debt_rel',
        # 'payment_group_id',
        # 'debt_line_id',
        related='to_pay_move_line_ids',
        string="Debt Lines",
        # no podemos ordenar por due date porque esta hardecodeado en
        # funcion _get_pair_to_reconcile
        help="Payment will be automatically matched with the oldest lines of "
        "this list (by date, no by maturity date). You can remove any line you"
        " dont want to be matched.",
        # copy=False,
        # domain=move_lines_domain,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    to_pay_move_line_ids = fields.Many2many(
        'account.move.line',
        'account_move_line_payment_group_to_pay_rel',
        'payment_group_id',
        'to_pay_line_id',
        string="To Pay Lines",
        help='This lines are the ones the user has selected to be paid.',
        copy=False,
        domain=move_lines_domain,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    matched_move_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_matched_move_line_ids',
        help='Lines that has been matched to payments, only available after '
        'payment validation',
    )
    payment_subtype = fields.Char(
        compute='_compute_payment_subtype'
    )

    @api.multi
    @api.depends('company_id.double_validation', 'partner_type')
    def _compute_payment_subtype(self):
        for rec in self:
            if (rec.partner_type == 'supplier' and
                    rec.company_id.double_validation):
                payment_subtype = 'double_validation'
            else:
                payment_subtype = 'simple'
            rec.payment_subtype = payment_subtype

    @api.one
    def _compute_matched_move_line_ids(self):
        # code taken from odoo core
        ids = []
        for aml in self.payment_ids.mapped('move_line_ids'):
            if aml.account_id.reconcile:
                ids.extend(
                    [r.debit_move_id.id for r in aml.matched_debit_ids] if
                    aml.credit > 0 else [
                        r.credit_move_id.id for r in aml.matched_credit_ids])
                # this is the payment line, we dont want it
                # ids.append(aml.id)
        self.matched_move_line_ids = self.env['account.move.line'].browse(ids)

    payment_difference = fields.Monetary(
        compute='_compute_payment_difference',
        # TODO rename field or remove string
        # string='Remaining Residual',
        readonly=True,
        string="Payment Difference",
    )
    # TODO por ahora no implementamos
    # payment_difference_handling = fields.Selection(
    #     [('open', 'Keep open'), ('reconcile', 'Mark invoice as fully paid')],
    #     default='open',
    #     string="Payment Difference",
    #     copy=False
    # )
    # TODO add journal?
    # writeoff_account_id = fields.Many2one(
    #     'account.account',
    #     string="Difference Account",
    #     domain=[('deprecated', '=', False)],
    #     copy=False
    # )
    payment_ids = fields.One2many(
        'account.payment',
        'payment_group_id',
        string='Payment Lines',
        ondelete='cascade',
        copy=False,
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]},
    )
    move_line_ids = fields.One2many(
        related='payment_ids.move_line_ids',
        readonly=True,
        copy=False,
    )
    account_internal_type = fields.Char(
        compute='_compute_account_internal_type'
    )

    @api.multi
    @api.depends('partner_type')
    def _compute_account_internal_type(self):
        for rec in self:
            if rec.partner_type:
                rec.account_internal_type = MAP_PARTNER_TYPE_ACCOUNT_TYPE[
                    rec.partner_type]

    @api.multi
    @api.depends('to_pay_amount', 'payments_amount')
    def _compute_payment_difference(self):
        for rec in self:
            # if rec.payment_subtype != 'double_validation':
            #     continue
            rec.payment_difference = rec.to_pay_amount - rec.payments_amount

    @api.multi
    @api.depends('payment_ids')
    def _compute_payments_amount(self):
        for rec in self:
            payments_amount = sum([
                x.payment_type == 'inbound' and x.amount or -x.amount for
                x in rec.payment_ids])
            rec.payments_amount = (
                rec.partner_type == 'supplier' and
                -payments_amount or payments_amount)

    @api.one
    @api.onchange(
        'to_pay_move_line_ids',
        'payment_date',
        'currency_id',
    )
    @api.constrains(
        'to_pay_move_line_ids',
        'payment_date',
        'currency_id',
    )
    def set_selected_debt(self):
        # we dont make it computed because we want to store value.
        # TODO check if odoo implement this kind of hybrid field
        payment_currency = self.currency_id or self.company_id.currency_id

        total = 0
        for rml in self.to_pay_move_line_ids:
            # si tiene moneda y es distinta convertimos el monto de moneda
            # si tiene moneda y es igual llevamos el monto de moneda
            # si no tiene moneda y es distinta convertimos el monto comun
            # si no tiene moneda y es igual llevamos el monto comun
            if rml.currency_id:
                if rml.currency_id != payment_currency:
                    total += rml.currency_id.with_context(
                        date=self.payment_date).compute(
                        rml.amount_residual_currency, payment_currency)
                else:
                    total += rml.amount_residual_currency
            else:
                if self.company_id.currency_id != payment_currency:
                    total += self.company_id.currency_id.with_context(
                        date=self.payment_date).compute(
                        rml.amount_residual, payment_currency)
                else:
                    total += rml.amount_residual
        self.selected_debt = abs(total)

    @api.multi
    @api.depends(
        'selected_debt', 'unreconciled_amount')
    def _compute_to_pay_amount(self):
        for rec in self:
            rec.to_pay_amount = rec.selected_debt + rec.unreconciled_amount

    @api.multi
    def _inverse_to_pay_amount(self):
        for rec in self:
            rec.unreconciled_amount = rec.to_pay_amount - rec.selected_debt

    @api.onchange('partner_id', 'partner_type')
    def _refresh_payments_and_move_lines(self):
        # clean actual invoice and payments
        # no hace falta
        if self._context.get('pop_up'):
            return
        self.payment_ids.unlink()
        self.add_all()
        # if self.payment_subtype == 'double_validation':
        #     self._add_all('to_pay_move_line_ids')
        # else:
        #     self._add_all('debt_move_line_ids')
        # if self.to_pay_move_line_ids:
        #     raise UserError('asdasdasd')
        # else:
        #     self.debt_move_line_ids = False
        #     self.payment_ids.unlink()
        #     self.add_all()

    @api.multi
    def add_all(self):
        for rec in self:
            # TODO ver si es necesario agregar un remove o el update las borra
            domain = [
                ('partner_id.commercial_partner_id', '=',
                    rec.commercial_partner_id.id),
                ('account_id.internal_type', '=',
                    rec.account_internal_type),
                ('account_id.reconcile', '=', True),
                ('reconciled', '=', False),
                # '|',
                # ('amount_residual', '!=', False),
                # ('amount_residual_currency', '!=', False),
            ]
            rec.to_pay_move_line_ids = rec.env['account.move.line'].search(
                domain)

    @api.multi
    def remove_all(self):
        self.to_pay_move_line_ids = False

    @api.model
    def default_get(self, fields):
        # TODO si usamos los move lines esto no haria falta
        rec = super(AccountPaymentGroup, self).default_get(fields)
        to_pay_move_line_ids = self._context.get('to_pay_move_line_ids')
        to_pay_move_lines = self.env['account.move.line'].browse(
            to_pay_move_line_ids).filtered(lambda x: (
                x.account_id.reconcile and
                x.account_id.internal_type in ('receivable', 'payable')))
        if to_pay_move_lines:
            partner = to_pay_move_lines.mapped('partner_id')
            print 'to_pay_move_lines', to_pay_move_lines
            if len(partner) != 1:
                raise ValidationError(_(
                    'You can not send to pay lines from different partners'))

            print 'partner', partner
            internal_type = to_pay_move_lines.mapped(
                'account_id.internal_type')
            if len(internal_type) != 1:
                raise ValidationError(_(
                    'You can not send to pay lines from different partners'))
            print 'partner', partner
            rec['partner_id'] = partner[0].id
            rec['partner_type'] = MAP_ACCOUNT_TYPE_PARTNER_TYPE[
                internal_type[0]]
            # rec['currency_id'] = invoice['currency_id'][0]
            # rec['payment_type'] = (
            #     internal_type[0] == 'receivable' and
            #     'inbound' or 'outbound')
            rec['to_pay_move_line_ids'] = [(6, False, to_pay_move_line_ids)]
        return rec
        # print 'rec', rec
        # invoice_defaults = self.resolve_2many_commands(
        #     'invoice_ids', rec.get('invoice_ids'))
        # print 'aaaaaa'
        # print 'aaaaaa', self._context
        # print 'aaaaaa', invoice_defaults
        # print 'aaaaaa', invoice_defaults
        # if invoice_defaults and len(invoice_defaults) == 1:
        #     invoice = invoice_defaults[0]
        #     rec['communication'] = invoice[
        #         'reference'] or invoice['name'] or invoice['number']
        #     rec['currency_id'] = invoice['currency_id'][0]
        #     rec['payment_type'] = invoice['type'] in (
        #         'out_invoice', 'in_refund') and 'inbound' or 'outbound'
        #     rec['partner_type'] = MAP_INVOICE_TYPE_PARTNER_TYPE[
        #         invoice['type']]
        #     rec['partner_id'] = invoice['partner_id'][0]
        #     # rec['amount'] = invoice['residual']
        # print 'rec', rec

    @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('payment_id', 'in', self.payment_ids.ids)],
        }

    @api.multi
    def unreconcile(self):
        for rec in self:
            rec.payment_ids.unreconcile()
            # TODO en alguos casos setear sent como en payment?
            rec.write({'state': 'posted'})

    @api.multi
    def cancel(self):
        for rec in self:
            # because child payments dont have invoices we remove reconcile
            for move in rec.move_line_ids.mapped('move_id'):
                rec.matched_move_line_ids.remove_move_reconcile()
                # TODO borrar esto si con el de arriba va bien
                # if rec.to_pay_move_line_ids:
                #     move.line_ids.remove_move_reconcile()
            rec.payment_ids.cancel()
            rec.state = 'draft'

    @api.multi
    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_(
                "You can not delete a payment that is already posted"))
        return super(AccountPaymentGroup, self).unlink()

    @api.multi
    def confirm(self):
        for rec in self:
            rec.state = 'confirmed'

    @api.multi
    def post(self):
        for rec in self:
            # TODO if we want to allow writeoff then we can disable this
            # constrain and send writeoff_journal_id and writeoff_acc_id
            if not rec.payment_ids:
                raise ValidationError(_(
                    'You can not confirm a payment group without payment '
                    'lines!'))
            if (rec.payment_subtype == 'double_validation' and
                    rec.payment_difference):
                raise ValidationError(_(
                    'To Pay Amount and Payment Amount must be equal!'))

            writeoff_acc_id = False
            writeoff_journal_id = False

            rec.payment_ids.post()
            counterpart_aml = rec.payment_ids.mapped('move_line_ids').filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))
            (counterpart_aml + (rec.to_pay_move_line_ids)).reconcile(
                writeoff_acc_id, writeoff_journal_id)
            rec.state = 'posted'
