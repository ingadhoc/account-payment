# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp.exceptions import Warning
from openerp import models, fields, api, _


class account_check_action(models.TransientModel):
    _name = 'account.check.action'

    # @api.model
    # def _get_company_id(self):
    #     active_ids = self._context.get('active_ids', [])
    #     checks = self.env['account.check'].browse(active_ids)
    #     company_ids = [x.company_id.id for x in checks]
    #     if len(set(company_ids)) > 1:
    #         raise Warning(_('All checks must be from the same company!'))
    #     return self.env['res.company'].search(
    #         [('id', 'in', company_ids)], limit=1)

    # journal_id = fields.Many2one(
    #     'account.journal',
    #     'Journal',
    #     domain="[('company_id','=',company_id), "
    #     "('type', 'in', ['cash', 'bank', 'general']), "
    #     "('payment_subtype', 'not in', ['issue_check', 'third_check'])]"
    # )
    # account_id = fields.Many2one(
    #     'account.account',
    #     'Account',
    #     domain="[('company_id','=',company_id), "
    #     "('type', 'in', ('other', 'liquidity'))]"
    # )
    reject_with = fields.Selection(
        [('debit_note', 'Debit Note'), ('account.move', 'Journal Entry')],
        'Reject With',
        required=True,
    )
    date = fields.Date(
        'Date', required=True, default=fields.Date.context_today
    )
    action_type = fields.Char(
        'Action type passed on the context', required=True
    )
    # company_id = fields.Many2one(
    #     'res.company',
    #     'Company',
    #     required=True,
    #     default=_get_company_id
    # )

    # @api.onchange('journal_id')
    # def onchange_journal_id(self):
    #     self.account_id = self.journal_id.default_debit_account_id.id

    @api.model
    def validate_action(self, action_type, check):
        # state controls
        if action_type == 'deposit':
            if check.type == 'third_check':
                if check.state != 'holding':
                    raise Warning(
                        _('The selected checks must be in holding state.'))
            else:   # issue
                raise Warning(_('You can not deposit a Issue Check.'))
        # if action_type == 'debit':
        elif action_type == 'debit':
            if check.type == 'issue_check':
                if check.state != 'handed':
                    raise Warning(
                        _('The selected checks must be in handed state.'))
            else:   # third
                raise Warning(_('You can not debit a Third Check.'))
        elif action_type == 'return':
            if check.type == 'third_check':
                if check.state != 'holding':
                    raise Warning(
                        _('The selected checks must be in holding state.'))
            # TODO implement return issue checs and return handed third checks
            else:   # issue
                raise Warning(_('You can not return a Issue Check.'))
        return True

    @api.multi
    def action_confirm(self):
        self.ensure_one()

        # used to get correct ir properties
        self = self.with_context(
            company_id=self.company_id.id,
            force_company=self.company_id.id,
        )

        for check in self.env['account.check'].browse(
                self._context.get('active_ids', [])):

            self.validate_action(self.action_type, check)

            vals = self.get_vals(self.action_type, check, self.date)

            # extraemos los vals
            move_vals = vals.get('move_vals', {})
            debit_line_vals = vals.get('debit_line_vals', {})
            credit_line_vals = vals.get('credit_line_vals', {})
            check_move_field = vals.get('check_move_field')
            signal = vals.get('signal')

            move = self.env['account.move'].with_context({}).create(move_vals)
            debit_line_vals['move_id'] = move.id
            credit_line_vals['move_id'] = move.id

            move.line_id.with_context({}).create(debit_line_vals)
            move.line_id.with_context({}).create(credit_line_vals)

            check.write({check_move_field: move.id})
            check.signal_workflow(signal)
            move.button_validate()
        return True

    @api.model
    def get_vals(self, action_type, check, date):
        period = self.env['account.period'].find(
            date)
        if not period:
            raise Warning(_('Not period found for this date'))
        period_id = period.id

        vou_journal = check.voucher_id.journal_id
        # TODO improove how we get vals, get them in other functions
        # if self.action_type == 'deposit':
        #     ref = _('Deposit Check Nr. ')
        #     check_move_field = 'deposit_account_move_id'
        #     journal = self.journal_id
        #     debit_account_id = self.account_id.id
        #     partner = check.source_partner_id.id,
        #     credit_account_id = vou_journal.default_credit_account_id.id
        #     signal = 'holding_deposited'
        # elif self.action_type == 'debit':
        if self.action_type == 'debit':
            ref = _('Debit Check Nr. ')
            check_move_field = 'debit_account_move_id'
            journal = check.checkbook_id.debit_journal_id
            partner = check.destiny_partner_id.id
            credit_account_id = journal.default_debit_account_id.id
            debit_account_id = vou_journal.default_credit_account_id.id
            signal = 'handed_debited'
        # elif self.action_type == 'return':
        #     ref = _('Return Check Nr. ')
        #     check_move_field = 'return_account_move_id'
        #     journal = vou_journal
        #     debit_account_id = (
        #         check.source_partner_id.property_account_receivable.id)
        #     partner = check.source_partner_id.id,
        #     credit_account_id = vou_journal.default_credit_account_id.id
        #     signal = 'holding_returned'

        name = self.env['ir.sequence'].next_by_id(
            journal.sequence_id.id)
        ref += check.name

        move_vals = {
            'name': name,
            'journal_id': journal.id,
            'period_id': period_id,
            'date': self.date,
            'ref': ref,
        }

        debit_line_vals = {
            'name': name,
            'account_id': debit_account_id,
            'partner_id': partner,
            'debit': check.company_currency_amount or check.amount,
            'amount_currency': (
                check.company_currency_amount and check.amount or False),
            'ref': ref,
        }
        credit_line_vals = {
            'name': name,
            'account_id': credit_account_id,
            'partner_id': partner,
            'credit': check.company_currency_amount or check.amount,
            'amount_currency': (
                check.company_currency_amount and (
                    -1 * check.amount) or False),
            'ref': ref,
        }
        return {
            'move_vals': move_vals,
            'debit_line_vals': debit_line_vals,
            'credit_line_vals': credit_line_vals,
            'check_move_field': check_move_field,
            'signal': signal,
        }
