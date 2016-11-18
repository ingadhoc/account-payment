# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _
from openerp.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    check_deposit_id = fields.Many2one(
        'account.payment',
        string='Check Deposit',
        copy=False
    )
    check_type = fields.Selection(
        [('issue_check', 'Issue Check'), ('third_check', 'Third Check')],
    )
    check_payment_date = fields.Date(
        related='date_maturity'
    )
    check_issue_date = fields.Date(
        # required=True,
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        default=fields.Date.context_today,
    )
    check_state = fields.Selection([
        # ('draft', 'Draft'),
        ('holding', 'Holding'),
        ('deposited', 'Deposited'),
        ('handed', 'Handed'),
        ('rejected', 'Rejected'),
        ('debited', 'Debited'),
        ('returned', 'Returned'),
        ('changed', 'Changed'),
        # ('cancel', 'Cancel'),
    ],
        # required=True,
        # track_visibility='onchange',
        # default='draft',
        default='holding',
        # compute='_compute_check_state'
        # copy=False,
    )
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        # TODO hacer con un onchange
        # default=_get_checkbook,
    )
    check_number = fields.Integer(
        # required=True,
        # readonly=True,
        copy=False
    )
    # @api.one
    # def _compute_check_state(self):
    #     state = False
    #     # por ahora implementamos los third checks
    #     if self.check_type == 'third_check':
    #         # default state
    #         self.state = 'holding'
    #         if self.
    #     # if self.payment_method_code == 'received_third_check':
    #     #     if self.state == 'draft':
    #     #         state = 'draft'
    #     #     elif self.state == 'posted':
    #     #         state = 'holding'
    #     self.check_state = state
    check_bank_id = fields.Many2one(
        'res.bank', 'Bank',
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )
    # currency_id = fields.Many2one(
    #     'res.currency',
    #     string='Currency',
    #     readonly=True,
    #     related='voucher_id.journal_id.currency',
    # )
    check_owner_vat = fields.Char(
        # TODO rename to Owner VAT
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )
    check_owner_name = fields.Char(
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )

    @api.multi
    @api.constrains(
        'check_type',
        'check_owner_name',
        'check_bank_id',
        # 'check_number'
    )
    def _check_unique(self):
        for rec in self:
            if rec.check_type == 'issue_check':
                same_checks = self.search([
                    ('checkbook_id', '=', rec.checkbook_id.id),
                    ('check_type', '=', rec.check_type),
                    ('check_number', '=', rec.check_number),
                ])
                if same_checks:
                    raise UserError(_(
                        'Check Number must be unique per Checkbook!\n'
                        '* Same number checks move line ids: %s') % (
                        same_checks.ids))
            elif self.check_type == 'third_check':
                same_checks = self.search([
                    ('check_bank_id', '=', rec.check_bank_id.id),
                    ('check_owner_name', '=', rec.check_owner_name),
                    ('check_type', '=', rec.check_type),
                    ('check_number', '=', rec.check_number),
                ])
                if same_checks:
                    raise UserError(_(
                        'Check Number must be unique per Owner and Bank!\n'
                        '* Same number checks move line ids: %s') % (
                        same_checks.ids))
        return True


    # @api.multi
    # def action_hold(self):
    #     self.write({'state': 'holding'})
    #     return True

    # @api.multi
    # def action_deposit(self):
    #     self.write({'state': 'deposited'})
    #     return True

    # @api.multi
    # def action_return(self):
    #     self.write({'state': 'returned'})
    #     return True

    # @api.multi
    # def action_change(self):
    #     self.write({'state': 'changed'})
    #     return True

    # @api.multi
    # def action_hand(self):
    #     self.write({'state': 'handed'})
    #     return True

    # @api.multi
    # def action_reject(self):
    #     self.write({'state': 'rejected'})
    #     return True

    # @api.multi
    # def action_debit(self):
    #     self.write({'state': 'debited'})
    #     return True

    # @api.multi
    # def action_cancel_rejection(self):
    #     for check in self:
    #         if check.customer_reject_debit_note_id:
    #             raise UserError(_(
    #                 'To cancel a rejection you must first delete the customer '
    #                 'reject debit note!'))
    #         if check.supplier_reject_debit_note_id:
    #             raise UserError(_(
    #                 'To cancel a rejection you must first delete the supplier '
    #                 'reject debit note!'))
    #         if check.rejection_account_move_id:
    #             raise UserError(_(
    #                 'To cancel a rejection you must first delete Expense '
    #                 'Account Move!'))
    #         check.signal_workflow('cancel_rejection')
    #     return True

    # @api.multi
    # def action_cancel_debit(self):
    #     for check in self:
    #         if check.debit_account_move_id:
    #             raise UserError(_(
    #                 'To cancel a debit you must first delete Debit '
    #                 'Account Move!'))
    #         check.signal_workflow('debited_handed')
    #     return True

    # @api.multi
    # def action_cancel_deposit(self):
    #     for check in self:
    #         if check.deposit_account_move_id:
    #             raise UserError(_(
    #                 'To cancel a deposit you must first delete the Deposit '
    #                 'Account Move!'))
    #         check.signal_workflow('cancel_deposit')
    #     return True

    # @api.multi
    # def action_cancel_return(self):
    #     for check in self:
    #         if check.return_account_move_id:
    #             raise UserError(_(
    #                 'To cancel a deposit you must first delete the Return '
    #                 'Account Move!'))
    #         check.signal_workflow('cancel_return')
    #     return True

    # TODO implementar para caso issue y third
    # @api.multi
    # def action_cancel_change(self):
    #     for check in self:
    #         if check.replacing_check_id:
    #             raise UserError(_(
    #                 'To cancel a return you must first delete the replacing '
    #                 'check!'))
    #         check.signal_workflow('cancel_change')
    #     return True

    # @api.multi
    # def check_check_cancellation(self):
    #     for check in self:
    #         if check.type == 'issue_check' and check.state not in [
    #                 'draft', 'handed']:
    #             raise UserError(_(
    #                 'You can not cancel issue checks in states other than '
    #                 '"draft or "handed". First try to change check state.'))
    #         # third checks received
    #         elif check.type == 'third_check' and check.state not in [
    #                 'draft', 'holding']:
    #             raise UserError(_(
    #                 'You can not cancel third checks in states other than '
    #                 '"draft or "holding". First try to change check state.'))
    #         elif check.type == 'third_check' and check.third_handed_voucher_id:
    #             raise UserError(_(
    #                 'You can not cancel third checks that are being used on '
    #                 'payments'))
    #     return True

    # @api.multi
    # def action_cancel(self):
    #     self.write({'state': 'cancel'})
    #     return True
