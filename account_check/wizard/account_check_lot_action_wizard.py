##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, api, models, _
from odoo.exceptions import ValidationError


class AccountCheckLotActionWizard(models.TransientModel):
    _name = 'account.check.lot.action.wizard'
    _description = 'Account Check Lot Action Wizard'

    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    action_type = fields.Char(
        'Action type passed on the context',
        required=True,
    )
    lot_operation = fields.Char(
        string='Lot operation'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner'
    )
    debit_note = fields.Boolean(
        string='Debit note',
        default=False
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain=[('type', 'in', ['cash', 'bank'])]
    )
    expense_check_account_id = fields.Many2one(
        'account.account',
        'Account Expense',
        domain=lambda self: [('user_type_id', '=', self.env.ref('account.data_account_type_expenses').id)]
    )
    amount = fields.Monetary(
        currency_field='company_currency_id',
        string='Expense amount')
    amount_total = fields.Monetary(
        currency_field='company_currency_id',
        string='Amount total')

    communication = fields.Char(string='Memo')

    company_id = fields.Many2one(
        related='journal_id.company_id',
        readonly=True,
        store=True
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True
    )
    tax_id = fields.Many2one(
        'account.tax',
        string='Taxes',
        domain=[('type_tax_use', '=', 'purchase'),
                '|', ('active', '=', False),
                ('active', '=', True)]
    )

    @api.model
    def default_get(self, fields):
        # TODO si usamos los move lines esto no haria falta
        rec = super().default_get(fields)
        checks = self.env['account.check'].browse(
            self._context.get('active_ids'))
        if self._context.get('default_action_type') in ['used', 'deposited']:
            if len(checks.mapped('journal_id')) != 1:
                raise ValidationError(_(
                    'All checks must belong to the same journal'))
            if self._context.get('default_action_type') in ['used'] and any(
                    check.type == 'third_check' for check in checks):
                raise ValidationError(_(
                    'You can only use your issue checks.'))
        if self._context.get('default_action_type') == 'used':
            rec['partner_id'] = self.env.company.partner_id and self.env.company.partner_id.id or False
        if self._context.get('default_action_type') == 'selled':
            if len(checks.mapped('partner_id')) == 1:
                rec['partner_id'] = checks[0].partner_id.id
                rec['amount_total'] = sum(checks.mapped('amount'))
        if len(checks) > 1:
            sequence = self.env['ir.sequence'].search([('code', '=', 'sequence.lot.operation.check')])
            if sequence and not rec.get('lot_operation', False):
                rec['lot_operation'] = sequence.next_by_id()
        if self._context.get('default_action_type') in ['bank_debit'] and any(
                check.type == 'third_check' for check in checks):
            raise ValidationError(_(
                'You can only debit your issue checks.'))
        return rec

    def action_confirm(self):
        self.ensure_one()
        if self.action_type not in ['bank_debit', 'used', 'negotiated', 'selled', 'deposited']:
            raise ValidationError(_(
                'Action %s not supported on checks') % self.action_type)
        checks = self.env['account.check'].browse(
            self._context.get('active_ids'))
        if self.action_type in ['used', 'negotiated']:
            return getattr(
                checks.with_context(action_date=self.date,
                                   lot_operation=self.lot_operation,
                                   partner=self.partner_id), self.action_type)()
        elif self.action_type == 'selled':
            return getattr(
                checks.with_context(action_date=self.date,
                               lot_operation=self.lot_operation,
                               partner=self.partner_id,
                               expense_amount=self.amount,
                               debit_note=self.debit_note,
                               journal=self.journal_id,
                               expense_account=self.expense_check_account_id,
                               tax_ids=self.tax_id
                               ), self.action_type)()
        elif self.action_type == 'deposited':
            return getattr(
                checks.with_context(action_date=self.date,
                               lot_operation=self.lot_operation,
                               journal=self.journal_id,
                               communication=self.communication
                               ), self.action_type)()
        else:
            return getattr(
                checks.with_context(action_date=self.date,
                                   lot_operation=self.lot_operation), self.action_type)()
        return True
