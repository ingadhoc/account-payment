# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp.exceptions import Warning
from openerp import models, fields, api, _


class account_check_dreject(models.TransientModel):
    _name = 'account.check.dreject'

    @api.model
    def _get_company_id(self):
        active_ids = self._context.get('active_ids', [])
        checks = self.env['account.check'].browse(active_ids)
        company_ids = [x.company_id.id for x in checks]
        if len(set(company_ids)) > 1:
            raise Warning(_('All checks must be from the same company!'))
        return self.env['res.company'].search(
            [('id', 'in', company_ids)], limit=1)

    type = fields.Char(
        'Check Type')
    state = fields.Char(
        'Check State')
    reject_date = fields.Date(
        'Reject Date', required=True, default=fields.Date.context_today)
    expense_account = fields.Many2one(
        'account.account',
        'Expense Account',
        domain=[('type', 'in', ['other'])],
    )
    has_expense = fields.Boolean(
        'Has Expense', default=True)
    expense_amount = fields.Float(
        'Expense Amount')
    expense_to_customer = fields.Boolean(
        'Invoice Expenses to Customer')
    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        default=_get_company_id)

    @api.multi
    def action_dreject(self):
        self.ensure_one()

        # used to get correct ir properties
        self = self.with_context(
            company_id=self.company_id.id,
            force_company=self.company_id.id,
        )

        for check in self.env['account.check'].browse(
                self._context.get('active_ids', [])):
            if check.state not in ['deposited', 'handed']:
                raise Warning(
                    _('Only deposited or handed checks can be rejected.'))

            if check.type == 'third_check':
                customer_invoice = self.make_invoice(
                    'out_invoice', check)
                if self.has_expense and self.expense_to_customer:
                    self.make_expense_invoice_line(
                        customer_invoice, check)
                elif self.has_expense:
                    self.make_expenses_move(check)

            if check.state == 'handed':
                supplier_invoice = self.make_invoice(
                    'in_invoice', check)
                if self.has_expense:
                    self.make_expense_invoice_line(
                        supplier_invoice, check)
            check.signal_workflow('rejected')

    @api.multi
    def make_expense_invoice_line(self, invoice, check):
        self.ensure_one()
        name = _('Rejected Expenses, Check N: ') + check.name
        self.env['account.invoice.line'].create({
            'name': name,
            'origin': name,
            'invoice_id': invoice.id,
            'account_id': self.expense_account.id,
            'price_unit': self.expense_amount,
            'quantity': 1,
        })

    @api.multi
    def make_invoice(self, invoice_type, check):
        self.ensure_one()
        if invoice_type == 'in_invoice':
            debit_note_field = 'supplier_reject_debit_note_id'
            journal = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('type', '=', 'purchase')], limit=1)
            partner_id = check.destiny_partner_id.id
            partner_account_id = (
                check.voucher_id.partner_id.property_account_payable.id)
            account_id = (
                check.voucher_id.journal_id.default_credit_account_id.id)
        else:
            debit_note_field = 'customer_reject_debit_note_id'
            journal = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('type', '=', 'sale')], limit=1)
            partner_account_id = (
                check.voucher_id.partner_id.property_account_receivable.id)
            partner_id = check.voucher_id.partner_id.id
            if check.state == 'handed':
                account_id = (
                    check.voucher_id.journal_id.default_credit_account_id.id)
            else:
                deposit_move = check.deposit_account_move_id
                account_id = (
                    deposit_move.journal_id.default_credit_account_id.id)

        if not journal:
            raise Warning(_('No journal for rejection in company %s') %
                          (self.company_id.name))

        name = _('Check Rejected N: ')
        name += check.name
        invoice_vals = {
            'name': name,
            'origin': name,
            'type': invoice_type,
            'account_id': partner_account_id,
            'partner_id': partner_id,
            'date_invoice': self.reject_date,
            'company_id': self.company_id.id,
            'journal_id': journal.id,
        }

        invoice = self.env['account.invoice'].with_context(
            {'document_type': 'debit_note'}
        ).create(
            invoice_vals)
        check.write({debit_note_field: invoice.id})

        invoice_line_vals = {
            'name': name,
            'origin': name,
            'invoice_id': invoice.id,
            'account_id': account_id,
            'price_unit': check.amount,
            'quantity': 1,
        }

        invoice.invoice_line.create(invoice_line_vals)

        return invoice

    @api.multi
    def make_expenses_move(self, check):
        self.ensure_one()

        period = self.env['account.period'].find(
            self.reject_date)
        if not period:
            raise Warning(_('Not period found for this date'))
        period_id = period.id

        name = self.env['ir.sequence'].next_by_id(
            check.voucher_id.journal_id.sequence_id.id)

        ref = _('Check Rejected N: ')
        ref += check.name
        move = self.with_context({}).env['account.move'].create({
            'name': name,
            'journal_id': check.voucher_id.journal_id.id,
            'period_id': period_id,
            'date': self.reject_date,
            'ref': _('Rejected Check Nr. ') + check.name,
        })

        move.line_id.with_context({}).create({
            'name': name,
            'centralisation': 'normal',
            'account_id': self.expense_account.id,
            'move_id': move.id,
            'period_id': period_id,
            'debit': self.expense_amount,
            'ref': ref,
        })

        if check.state == 'handed':
            account_id = (
                check.voucher_id.journal_id.default_credit_account_id.id)
        else:
            deposit_move = check.deposit_account_move_id
            account_id = deposit_move.journal_id.default_credit_account_id.id
        move.line_id.with_context({}).create({
            'name': name,
            'centralisation': 'normal',
            'account_id': account_id,
            'move_id': move.id,
            'period_id': period_id,
            'credit': self.expense_amount,
            'ref': ref,
        })
        move.button_validate()
        check.write({'expense_account_move_id': move.id})
