# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import ValidationError


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
    _inherit = 'mail.thread'

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
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    payment_date = fields.Date(
        string='Payment Date',
        default=fields.Date.context_today,
        required=True,
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    communication = fields.Char(
        string='Memo',
        readonly=True,
        states={'draft': [('readonly', False)]},
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
        currency_field='currency_id',
    )
    unmatched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
        currency_field='currency_id',
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

    selected_finacial_debt = fields.Monetary(
        string='Selected Financial Debt',
        compute='_compute_selected_debt',
    )
    selected_debt = fields.Monetary(
        # string='To Pay lines Amount',
        string='Selected Debt',
        compute='_compute_selected_debt',
    )
    # this field is to be used by others
    selected_debt_untaxed = fields.Monetary(
        # string='To Pay lines Amount',
        string='Selected Debt Untaxed',
        compute='_compute_selected_debt',
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
        "('company_id', '=', company_id),"
        # '|',
        # ('amount_residual', '!=', False),
        # ('amount_residual_currency', '!=', False),
        "]")
    debt_move_line_ids = fields.Many2many(
        'account.move.line',
        # por alguna razon el related no funciona bien ni con states ni
        # actualiza bien con el onchange, hacemos computado mejor
        compute='_compute_debt_move_line_ids',
        inverse='_inverse_debt_move_line_ids',
        string="Debt Lines",
        # no podemos ordenar por due date porque esta hardecodeado en
        # funcion _get_pair_to_reconcile
        help="Payment will be automatically matched with the oldest lines of "
        "this list (by date, no by maturity date). You can remove any line you"
        " dont want to be matched.",
        domain=move_lines_domain,
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
        # lo hacemos readonly por vista y no por aca porque el relatd si no
        # no funcionaba bien
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
    pop_up = fields.Boolean(
        # campo que agregamos porque el  invisible="context.get('pop_up')"
        # en las pages no se comportaba bien con los attrs
        compute='_compute_payment_pop_up',
        default=lambda x: x._context.get('pop_up', False),
    )

    @api.multi
    @api.depends('to_pay_move_line_ids')
    def _compute_debt_move_line_ids(self):
        for rec in self:
            rec.debt_move_line_ids = rec.to_pay_move_line_ids

    @api.multi
    @api.onchange('debt_move_line_ids')
    def _inverse_debt_move_line_ids(self):
        for rec in self:
            rec.to_pay_move_line_ids = rec.debt_move_line_ids

    @api.multi
    def _compute_payment_pop_up(self):
        pop_up = self._context.get('pop_up', False)
        for rec in self:
            rec.pop_up = pop_up

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
        # TODO mejorar esta funcion buscando directamente en las partial
        # reconcile
        ids = []
        for aml in self.payment_ids.mapped('move_line_ids'):
            if aml.account_id.reconcile:
                ids.extend(
                    [r.debit_move_id.id for r in aml.matched_debit_ids] if
                    aml.credit > 0 else [
                        r.credit_move_id.id for r in aml.matched_credit_ids])
                # this is the payment line, we dont want it
                # ids.append(aml.id)
        self.matched_move_line_ids = self.env['account.move.line'].browse(
            list(set(ids)))

    payment_difference = fields.Monetary(
        compute='_compute_payment_difference',
        # TODO rename field or remove string
        # string='Remaining Residual',
        readonly=True,
        string="Payments Difference",
        help="Difference between selected debt (or to pay amount) and "
        "payments amount"
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
    @api.depends('payment_ids.amount_company_currency')
    def _compute_payments_amount(self):
        for rec in self:
            rec.payments_amount = sum(rec.payment_ids.mapped(
                'amount_company_currency'))
            # payments_amount = sum([
            #     x.payment_type == 'inbound' and
            #     x.amount_company_currency or -x.amount_company_currency for
            #     x in rec.payment_ids])
            # rec.payments_amount = (
            #     rec.partner_type == 'supplier' and
            #     -payments_amount or payments_amount)

    # TODO analizar en v10
    # el onchange no funciona bien en o2m, si usamos write se escribe pero no
    # se actualiza en interfaz lo cual puede ser confuzo, por ahora lo
    # comentamos
    # @api.onchange('payment_date')
    # def change_payment_date(self):
    #     # self.payment_ids.write({'payment_date': self.payment_date})
    #     for line in self.payment_ids:
    #         line.payment_date = self.payment_date

    @api.one
    # @api.onchange(
    @api.depends(
        # 'to_pay_move_line_ids',
        'to_pay_move_line_ids.amount_residual',
        'to_pay_move_line_ids.amount_residual_currency',
        'to_pay_move_line_ids.currency_id',
        'to_pay_move_line_ids.invoice_id',
        'payment_date',
        'currency_id',
    )
    # @api.constrains(
    #     'to_pay_move_line_ids',
    #     'payment_date',
    #     'currency_id',
    # )
    # def set_selected_debt(self):
    def _compute_selected_debt(self):
        # # we dont make it computed because we want to store value.
        # # TODO check if odoo implement this kind of hybrid field
        # payment_currency = self.currency_id or self.company_id.currency_id

        # total_untaxed = total = 0
        # for rml in self.to_pay_move_line_ids:
        #     # factor for total_untaxed
        #     invoice = rml.invoice_id
        #     factor = invoice and invoice._get_tax_factor() or 1.0

        #     # si tiene moneda y es distinta convertimos el monto de moneda
        #     # si tiene moneda y es igual llevamos el monto de moneda
        #     # si no tiene moneda y es distinta convertimos el monto comun
        #     # si no tiene moneda y es igual llevamos el monto comun
        #     if rml.currency_id:
        #         if rml.currency_id != payment_currency:
        #             line_amount = rml.currency_id.with_context(
        #                 date=self.payment_date).compute(
        #                 rml.amount_residual_currency, payment_currency)
        #         else:
        #             line_amount = rml.amount_residual_currency
        #     else:
        #         if self.company_id.currency_id != payment_currency:
        #             line_amount = self.company_id.currency_id.with_context(
        #                 date=self.payment_date).compute(
        #                 rml.amount_residual, payment_currency)
        #         else:
        #             line_amount = rml.amount_residual
        #     total += line_amount
        #     total_untaxed += line_amount * factor
        # self.selected_debt = abs(total)
        # self.selected_debt_untaxed = abs(total_untaxed)
        selected_finacial_debt = 0.0
        selected_debt = 0.0
        selected_debt_untaxed = 0.0
        for line in self.to_pay_move_line_ids:
            selected_finacial_debt += line.financial_amount_residual
            selected_debt += line.amount_residual
            # factor for total_untaxed
            invoice = line.invoice_id
            factor = invoice and invoice._get_tax_factor() or 1.0
            selected_debt_untaxed += line.amount_residual * factor
        sign = self.partner_type == 'supplier' and -1.0 or 1.0
        self.selected_finacial_debt = selected_finacial_debt * sign
        self.selected_debt = selected_debt * sign
        self.selected_debt_untaxed = selected_debt_untaxed * sign

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

    @api.onchange('partner_id', 'partner_type', 'company_id')
    def _refresh_payments_and_move_lines(self):
        # clean actual invoice and payments
        # no hace falta
        if self._context.get('pop_up'):
            return
        # not sure why but state field is false on payments so they can
        # not be unliked, this fix that
        self.invalidate_cache(['payment_ids'])
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
                ('company_id', '=', rec.company_id.id),
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
            if len(partner) != 1:
                raise ValidationError(_(
                    'You can not send to pay lines from different partners'))

            internal_type = to_pay_move_lines.mapped(
                'account_id.internal_type')
            if len(internal_type) != 1:
                raise ValidationError(_(
                    'You can not send to pay lines from different partners'))
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
            raise ValidationError(_(
                "You can not delete a payment that is already posted"))
        return super(AccountPaymentGroup, self).unlink()

    @api.multi
    def confirm(self):
        for rec in self:
            accounts = rec.to_pay_move_line_ids.mapped('account_id')
            if len(accounts) > 1:
                raise ValidationError(_(
                    'To Pay Lines must be of the same account!'))
            rec.state = 'confirmed'

    @api.multi
    def post(self):
        # dont know yet why, but if we came from an invoice context values
        # break behaviour, for eg. with demo user error writing account.account
        # and with other users, error with block date of accounting
        # TODO we should look for a better way to solve this
        self = self.with_context({})
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

    # @api.multi
    # def action_create_debit_credit_note(self):
    #     self.ensure_one()
    #     if self.partner_type == 'supplier':
    #         view_id = self.env.ref('account.invoice_supplier_form').id
    #         invoice_type = 'in_'
    #     else:
    #         view_id = self.env.ref('account.invoice_form').id
    #         invoice_type = 'out_'

    #     print 'self._context', self._context
    #     if self._context.get('refund'):
    #         name = _('Credit Note')
    #         invoice_type += 'refund'
    #         # for compatibility with account_document and loc ar
    #         internal_type = False
    #     else:
    #         name = _('Debit Note')
    #         invoice_type += 'invoice'
    #         internal_type = 'debit_note'

    #     return {
    #         'name': name,
    #         'view_type': 'form',
    #         'view_mode': 'form',
    #         'res_model': 'account.invoice',
    #         'view_id': view_id,
    #         'type': 'ir.actions.act_window',
    #         'context': {
    #             'default_partner_id': self.partner_id.id,
    #             'default_company_id': self.company_id.id,
    #             'default_type': invoice_type,
    #             'internal_type': internal_type,
    #         },
    #         # 'domain': [('payment_id', 'in', self.payment_ids.ids)],
    #     }
