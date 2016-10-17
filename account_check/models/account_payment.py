# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import fields, models, _, api
from openerp.exceptions import Warning
import logging
# import openerp.addons.decimal_precision as dp
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
# class account_check(models.Model):

    _inherit = 'account.payment'
    # _name = 'account.check'
    # _description = 'Account Check'
    # _order = "id desc"
    # _inherit = ['mail.thread']

    # @api.model
    # def _get_checkbook(self):
    #     journal_id = self._context.get('default_journal_id', False)
    #     payment_subtype = self._context.get('default_type', False)
    #     if journal_id and payment_subtype == 'issue_check':
    #         checkbooks = self.env['account.checkbook'].search(
    #             [('state', '=', 'active'), ('journal_id', '=', journal_id)])
    #         return checkbooks and checkbooks[0] or False

    # Odoo by default use communication to store check number
    deposited_check_ids = fields.One2many(
        'account.move.line',
        'check_deposit_id',
        string='Deposited Checks',
        readonly=True,
        states={'draft': [('readonly', '=', False)]}
    )

    @api.one
    @api.onchange('check_number', 'checkbook_id')
    # @api.depends('check_number', 'checkbook_id', 'checkbook_id.padding')
    # def _get_name(self):
    def change_check_number(self):
        # TODO make default padding a parameter
        if self.payment_method_code in ['received_third_check', 'issue_check']:
            padding = self.checkbook_id and self.checkbook_id.padding or 8
            if len(str(self.check_number)) > padding:
                padding = len(str(self.check_number))
            self.communication = _('Check nbr %s') % (
                '%%0%sd' % padding % self.check_number)

    # @api.one
    # @api.depends(
    #     'voucher_id',
    #     'voucher_id.partner_id',
    #     'type',
    #     'third_handed_voucher_id',
    #     'third_handed_voucher_id.partner_id',
    # )
    # def _get_destiny_partner(self):
    #     partner_id = False
    #     if self.type == 'third_check' and self.third_handed_voucher_id:
    #         partner_id = self.third_handed_voucher_id.partner_id.id
    #     elif self.type == 'issue_check':
    #         partner_id = self.voucher_id.partner_id.id
    #     self.destiny_partner_id = partner_id

    # @api.one
    # @api.depends(
    #     'voucher_id',
    #     'voucher_id.partner_id',
    #     'type',
    # )
    # def _get_source_partner(self):
    #     partner_id = False
    #     if self.type == 'third_check':
    #         partner_id = self.voucher_id.partner_id.id
    #     self.source_partner_id = partner_id

    # name = fields.Char(
    #     compute='_get_name',
    #     string=_('Number')
    # )
    check_number = fields.Char(
        'Number',
        # required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False
    )
    # amount = fields.Float(
    #     'Amount',
    #     required=True,
    #     readonly=True,
    #     digits=dp.get_precision('Account'),
    #     states={'draft': [('readonly', False)]},
    # )
    # company_currency_amount = fields.Float(
    #     'Company Currency Amount',
    #     readonly=True,
    #     digits=dp.get_precision('Account'),
    #     help='This value is only set for those checks that has a different '
    #     'currency than the company one.'
    # )
    # voucher_id = fields.Many2one(
    #     'account.voucher',
    #     'Voucher',
    #     readonly=True,
    #     required=True,
    #     ondelete='cascade',
    # )
    # type = fields.Selection(
    #     related='voucher_id.journal_id.payment_subtype',
    #     string='Type',
    #     readonly=True,
    #     store=True
    # )
    # journal_id = fields.Many2one(
    #     'account.journal',
    #     related='voucher_id.journal_id',
    #     string='Journal',
    #     readonly=True,
    #     store=True
    # )
    check_issue_date = fields.Date(
        'Issue Date',
        # required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=fields.Date.context_today,
    )
    check_payment_date = fields.Date(
        'Payment Date',
        readonly=True,
        help="Only if this check is post dated",
        states={'draft': [('readonly', False)]}
    )
    # destiny_partner_id = fields.Many2one(
    #     'res.partner',
    #     compute='_get_destiny_partner',
    #     string='Destiny Partner',
    #     store=True,
    # )
    # user_id = fields.Many2one(
    #     'res.users',
    #     'User',
    #     readonly=True,
    #     default=lambda self: self.env.user,
    # )
    # clearing = fields.Selection([
    #     ('24', '24 hs'),
    #     ('48', '48 hs'),
    #     ('72', '72 hs'),
    # ],
    #     'Clearing',
    #     readonly=True,
    #     states={'draft': [('readonly', False)]})
    check_state = fields.Selection([
        ('draft', 'Draft'),
        ('holding', 'Holding'),
        ('deposited', 'Deposited'),
        ('handed', 'Handed'),
        ('rejected', 'Rejected'),
        ('debited', 'Debited'),
        ('returned', 'Returned'),
        ('changed', 'Changed'),
        ('cancel', 'Cancel'),
    ],
        'Check State',
        # required=True,
        # track_visibility='onchange',
        default='draft',
        compute='_compute_check_state'
        # copy=False,
    )

    @api.one
    def _compute_check_state(self):
        state = False
        if self.payment_method_code == 'received_third_check':
            if self.state == 'draft':
                state = 'draft'
            elif self.state == 'posted':
                state = 'holding'
        self.check_state = state
    # supplier_reject_debit_note_id = fields.Many2one(
    #     'account.invoice',
    #     'Supplier Reject Debit Note',
    #     readonly=True,
    #     copy=False,
    # )
    # rejection_account_move_id = fields.Many2one(
    #     'account.move',
    #     'Rejection Account Move',
    #     readonly=True,
    #     oldname='expense_account_move_id',
    #     copy=False,
    # )
    # replacing_check_id = fields.Many2one(
    #     'account.check',
    #     'Replacing Check',
    #     readonly=True,
    #     copy=False,
    # )

    # Related fields
    # company_id = fields.Many2one(
    #     'res.company',
    #     related='voucher_id.company_id',
    #     string='Company',
    #     store=True,
    #     readonly=True
    # )

    # Issue Check
    # issue_check_subtype = fields.Selection(
    #     related='checkbook_id.issue_check_subtype',
    #     string='Subtype',
    #     readonly=True, store=True
    # )
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        readonly=True,
        states={'draft': [('readonly', False)]},
        # TODO hacer con un onchange
        # default=_get_checkbook,
    )
    # debit_account_move_id = fields.Many2one(
    #     'account.move',
    #     'Debit Account Move',
    #     readonly=True,
    #     copy=False,
    # )

    # Third check
    # third_handed_voucher_id = fields.Many2one(
    #     'account.voucher', 'Handed Voucher', readonly=True,)
    # source_partner_id = fields.Many2one(
    #     'res.partner',
    #     compute='_get_source_partner',
    #     string='Source Partner',
    #     store=True,
    # )
    # customer_reject_debit_note_id = fields.Many2one(
    #     'account.invoice',
    #     'Customer Reject Debit Note',
    #     readonly=True,
    #     copy=False
    # )
    check_bank_id = fields.Many2one(
        'res.bank', 'Bank',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    # currency_id = fields.Many2one(
    #     'res.currency',
    #     string='Currency',
    #     readonly=True,
    #     related='voucher_id.journal_id.currency',
    # )
    check_owner_vat = fields.Char(
        # TODO rename to Owner VAT
        'Owner Vat',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    check_owner_name = fields.Char(
        'Owner Name',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    # deposit_account_move_id = fields.Many2one(
    #     'account.move',
    #     'Deposit Account Move',
    #     readonly=True,
    #     copy=False
    # )
    # deposit_date = fields.Date(
    #     related='deposit_account_move_id.date',
    #     store=True,
    #     string='Fecha de Depósito',
    # )
    # account move of return
    # return_account_move_id = fields.Many2one(
    #     'account.move',
    #     'Return Account Move',
    #     readonly=True,
    #     copy=False
    # )

    # def _check_number_interval(self, cr, uid, ids, context=None):
    #     for obj in self.browse(cr, uid, ids, context=context):
    #         if obj.type != 'issue_check' or (
    #                 obj.checkbook_id and
    #                 obj.checkbook_id.range_from <= obj.number <=
    #                 obj.checkbook_id.range_to):
    #             return True
    #     return False

    # def _check_number_issue(self, cr, uid, ids, context=None):
    #     for obj in self.browse(cr, uid, ids, context=context):
    #         if obj.type == 'issue_check':
    #             same_number_check_ids = self.search(
    #                 cr, uid, [
    #                     ('id', '!=', obj.id),
    #                     ('number', '=', obj.number),
    #                     ('checkbook_id', '=', obj.checkbook_id.id)],
    #                 context=context)
    #             if same_number_check_ids:
    #                 return False
    #     return True

    # def _check_number_third(self, cr, uid, ids, context=None):
    #     for obj in self.browse(cr, uid, ids, context=context):
    #         if obj.type == 'third_check':
    #             same_number_check_ids = self.search(
    #                 cr, uid, [
    #                     ('id', '!=', obj.id),
    #                     ('number', '=', obj.number),
    #                     ('voucher_id.partner_id', '=',
    #                         obj.voucher_id.partner_id.id)], context=context)
    #             if same_number_check_ids:
    #                 return False
    #     return True

    # _constraints = [
    #     (_check_number_issue,
    #         'Check Number must be unique per Checkbook!',
    #         ['number', 'checkbook_id', 'type']),
    #     (_check_number_third,
    #         'Check Number must be unique per Owner and Bank!',
    #         ['number', 'bank_id', 'owner_name', 'type']),
    # ]

    @api.one
    @api.constrains('check_issue_date', 'check_payment_date')
    @api.onchange('check_issue_date', 'check_payment_date')
    def onchange_date(self):
        if (
                self.check_issue_date and self.check_payment_date and
                self.check_issue_date > self.check_payment_date):
            self.check_payment_date = False
            raise Warning(
                _('Check Payment Date must be greater than Issue Date'))

    @api.one
    @api.onchange('partner_id')
    def onchange_voucher(self):
        self.check_owner_name = self.partner_id.name
        # TODO use document number instead of vat?
        self.check_owner_vat = self.partner_id.vat

    def _get_liquidity_move_line_vals(self, amount):
        vals = super(AccountPayment, self)._get_liquidity_move_line_vals(
            amount)
        if self.payment_method_code in [
                'received_third_check',
                'delivered_third_check',
                'issue_check']:
            vals['date_maturity'] = self.check_payment_date
            vals['check_bank_id'] = self.check_bank_id.id
            vals['check_owner_name'] = self.check_owner_name
            vals['check_owner_vat'] = self.check_owner_vat
            vals['checkbook_id'] = self.checkbook_id.id
            vals['check_issue_date'] = self.check_issue_date
            if self.payment_method_code == 'issue_check':
                vals['check_type'] = 'issue_check'
            else:
                vals['check_type'] = 'third_check'
        return vals
    # @api.one
    # def unlink(self):
    #     if self.state not in ('draft'):
    #         raise Warning(
    #             _('The Check must be in draft state for unlink !'))
    #     return super(account_check, self).unlink()

    # @api.one
    # @api.onchange('checkbook_id')
    # def onchange_checkbook(self):
    #     if self.checkbook_id:
    #         self.number = self.checkbook_id.next_check_number

    # @api.multi
    # def action_cancel_draft(self):
    #     # go from canceled state to draft state
    #     self.write({'state': 'draft'})
    #     self.delete_workflow()
    #     self.create_workflow()
    #     return True

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
    #             raise Warning(_(
    #                 'To cancel a rejection you must first delete the customer '
    #                 'reject debit note!'))
    #         if check.supplier_reject_debit_note_id:
    #             raise Warning(_(
    #                 'To cancel a rejection you must first delete the supplier '
    #                 'reject debit note!'))
    #         if check.rejection_account_move_id:
    #             raise Warning(_(
    #                 'To cancel a rejection you must first delete Expense '
    #                 'Account Move!'))
    #         check.signal_workflow('cancel_rejection')
    #     return True

    # @api.multi
    # def action_cancel_debit(self):
    #     for check in self:
    #         if check.debit_account_move_id:
    #             raise Warning(_(
    #                 'To cancel a debit you must first delete Debit '
    #                 'Account Move!'))
    #         check.signal_workflow('debited_handed')
    #     return True

    # @api.multi
    # def action_cancel_deposit(self):
    #     for check in self:
    #         if check.deposit_account_move_id:
    #             raise Warning(_(
    #                 'To cancel a deposit you must first delete the Deposit '
    #                 'Account Move!'))
    #         check.signal_workflow('cancel_deposit')
    #     return True

    # @api.multi
    # def action_cancel_return(self):
    #     for check in self:
    #         if check.return_account_move_id:
    #             raise Warning(_(
    #                 'To cancel a deposit you must first delete the Return '
    #                 'Account Move!'))
    #         check.signal_workflow('cancel_return')
    #     return True

    # TODO implementar para caso issue y third
    # @api.multi
    # def action_cancel_change(self):
    #     for check in self:
    #         if check.replacing_check_id:
    #             raise Warning(_(
    #                 'To cancel a return you must first delete the replacing '
    #                 'check!'))
    #         check.signal_workflow('cancel_change')
    #     return True

    # @api.multi
    # def check_check_cancellation(self):
    #     for check in self:
    #         if check.type == 'issue_check' and check.state not in [
    #                 'draft', 'handed']:
    #             raise Warning(_(
    #                 'You can not cancel issue checks in states other than '
    #                 '"draft or "handed". First try to change check state.'))
    #         # third checks received
    #         elif check.type == 'third_check' and check.state not in [
    #                 'draft', 'holding']:
    #             raise Warning(_(
    #                 'You can not cancel third checks in states other than '
    #                 '"draft or "holding". First try to change check state.'))
    #         elif check.type == 'third_check' and check.third_handed_voucher_id:
    #             raise Warning(_(
    #                 'You can not cancel third checks that are being used on '
    #                 'payments'))
    #     return True

    # @api.multi
    # def action_cancel(self):
    #     self.write({'state': 'cancel'})
    #     return True
