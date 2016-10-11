# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import UserError, ValidationError
MAP_PARTNER_TYPE_INVOICE_TYPES = {
    'customer': ['out_invoice', 'out_refund'],
    'supplier': ['in_invoice', 'in_refund'],
}
# TODO import this one
MAP_INVOICE_TYPE_PARTNER_TYPE = {
    'out_invoice': 'customer',
    'out_refund': 'customer',
    'in_invoice': 'supplier',
    'in_refund': 'supplier',
}


class AccountPaymentMulti(models.Model):
    _name = "account.payment.multi"
    _description = "Payments"
    _order = "payment_date desc, name desc"

    payment_type = fields.Selection([('outbound', 'Send Money'), ('inbound', 'Receive Money')], string='Payment Type', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, default=lambda self: self.env.user.company_id)
    partner_type = fields.Selection([('customer', 'Customer'), ('supplier', 'Vendor')])
    partner_id = fields.Many2one('res.partner', string='Partner')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.user.company_id.currency_id)
    payment_date = fields.Date(string='Payment Date', default=fields.Date.context_today, required=True, copy=False)
    communication = fields.Char(string='Memo')

    unreconciled_amount = fields.Monetary()
    reconciled_amount = fields.Monetary(readonly=True)
    # reconciled_amount = fields.Monetary(compute='_compute_amounts')
    to_pay_amount = fields.Monetary(compute='_compute_to_pay_amount')
    payments_amount = fields.Monetary(compute='_compute_payments_amount')

    name = fields.Char(readonly=True, copy=False, default="Draft Payment") # The name is attributed upon post()
    state = fields.Selection([('draft', 'Draft'), ('posted', 'Posted'), ('sent', 'Sent'), ('reconciled', 'Reconciled')], readonly=True, default='draft', copy=False, string="Status")

    invoice_ids = fields.Many2many('account.invoice', 'account_invoice_payment_multi_rel', 'payment_id', 'invoice_id', string="Invoices", copy=False,)
    reconciled_move_line_ids = fields.Many2many(
        'account.move.line', 'account_move_line_payment_multi_rel', 'payment_multi_id', 'move_line_id', string="Reconciled Lines", copy=False,)
    payment_difference = fields.Monetary(compute='_compute_payment_difference', readonly=True)
    payment_difference_handling = fields.Selection([('open', 'Keep open'), ('reconcile', 'Mark invoice as fully paid')], default='open', string="Payment Difference", copy=False)
    # TODO add journal?
    writeoff_account_id = fields.Many2one('account.account', string="Difference Account", domain=[('deprecated', '=', False)], copy=False)

    payment_ids = fields.One2many('account.payment', 'payment_multi_id', string='Payments')
    # payment_ids = fields.One2many('account.payment', 'payment_multi_id', copy=False, ondelete='cascade')
    move_line_ids = fields.One2many(related='payment_ids.move_line_ids', readonly=True, copy=False)

    @api.one
    @api.depends('to_pay_amount', 'payments_amount')
    def _compute_payment_difference(self):
        self.payment_difference = self.to_pay_amount - self.payments_amount

    @api.one
    @api.depends('payment_ids')
    def _compute_payments_amount(self):
        self.payments_amount = sum(self.payment_ids.mapped('amount'))

    # TODO borrar reconciled_move_line_ids o invoice_ids
    @api.one
    @api.onchange(
        'invoice_ids', 'reconciled_move_line_ids', 'payment_date', 'currency_id',)
    @api.constrains(
        'invoice_ids', 'reconciled_move_line_ids', 'payment_date', 'currency_id',)
    def set_reconciled_amount(self):
        # we dont make it computed because we want to store value.
        # TODO check if odoo implement this kind of hybrid field
        payment_currency = self.currency_id or self.company_id.currency_id

        if self.reconciled_move_line_ids:
            total = 0
            for rml in self.reconciled_move_line_ids:
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
        else:
            invoices = self._get_invoices()
            if all(inv.currency_id == payment_currency for inv in invoices):
                total = sum(invoices.mapped('residual_signed'))
            else:
                total = 0
                for inv in invoices:
                    if inv.company_currency_id != payment_currency:
                        total += inv.company_currency_id.with_context(
                            date=self.payment_date).compute(
                            inv.residual_company_signed, payment_currency)
                    else:
                        total += inv.residual_company_signed
        self.reconciled_amount = abs(total)

    @api.one
    @api.depends(
        'reconciled_amount', 'unreconciled_amount')
    def _compute_to_pay_amount(self):
        self.to_pay_amount = self.reconciled_amount + self.unreconciled_amount

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        # Set partner_id domain
        if self.partner_type:
            return {'domain': {'partner_id': [(self.partner_type, '=', True)]}}

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        # clean actual payments
        self.payment_ids.unlink()
        if not self.invoice_ids:
            # Set default partner type for the payment type
            if self.payment_type == 'inbound':
                self.partner_type = 'customer'
            elif self.payment_type == 'outbound':
                self.partner_type = 'supplier'

    @api.onchange('partner_id', 'partner_type')
    def _get_invoice_domain(self):
        # clean actual invoice and payments
        self.reconciled_move_line_ids = False
        self.invoice_ids = False
        self.payment_ids.unlink()
        if self.partner_id and self.partner_type:
            inv_types = MAP_PARTNER_TYPE_INVOICE_TYPES[self.partner_type]
            commercial_partner = self.partner_id.commercial_partner_id
            return {'domain': {
                'invoice_ids': [
                    ('commercial_partner_id', '=', commercial_partner.id),
                    ('type', 'in', inv_types),
                    ('state', '=', 'open'),
                ],
                'reconciled_move_line_ids': [
                    ('partner_id.commercial_partner_id', '=',
                        commercial_partner.id),
                    # TODO agregar filtro de cuenta o algo
                    # ('type', 'in', inv_types),
                    ('reconciled', '=', False),
                    # '|',
                    # ('amount_residual', '!=', False),
                    # ('amount_residual_currency', '!=', False),
                ],
            }}

    @api.model
    def default_get(self, fields):
        # TODO si usamos los move lines esto no haria falta
        rec = super(AccountPaymentMulti, self).default_get(fields)
        invoice_defaults = self.resolve_2many_commands(
            'invoice_ids', rec.get('invoice_ids'))
        if invoice_defaults and len(invoice_defaults) == 1:
            invoice = invoice_defaults[0]
            rec['communication'] = invoice[
                'reference'] or invoice['name'] or invoice['number']
            rec['currency_id'] = invoice['currency_id'][0]
            rec['payment_type'] = invoice['type'] in (
                'out_invoice', 'in_refund') and 'inbound' or 'outbound'
            rec['partner_type'] = MAP_INVOICE_TYPE_PARTNER_TYPE[
                invoice['type']]
            rec['partner_id'] = invoice['partner_id'][0]
            # rec['amount'] = invoice['residual']
        return rec

    def _get_invoices(self):
        # TODO si usamos los move lines esto no haria falta
        return self.invoice_ids

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

    # @api.multi
    # def button_invoices(self):
    #     return {
    #         'name': _('Paid Invoices'),
    #         'view_type': 'form',
    #         'view_mode': 'tree',
    #         'res_model': 'account.invoice',
    #         'view_id': False,
    #         'type': 'ir.actions.act_window',
    #         'domain': [('id', 'in', [x.id for x in self.invoice_ids])],
    #     }

    @api.multi
    def button_dummy(self):
        return True

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
                if rec.invoice_ids:
                    move.line_ids.remove_move_reconcile()
            rec.payment_ids.cancel()
            rec.state = 'draft'

    @api.multi
    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_(
                "You can not delete a payment that is already posted"))
        return super(AccountPaymentMulti, self).unlink()

    @api.multi
    def post(self):
        for rec in self:
            rec.payment_ids.post()
            counterpart_aml = rec.move_line_ids.filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))
            rec.invoice_ids.register_payment(counterpart_aml)
            rec.state = 'posted'
