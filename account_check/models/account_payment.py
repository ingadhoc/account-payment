# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import fields, models, _, api
from openerp.exceptions import UserError
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
    readonly_currency_id = fields.Many2one(
        related='currency_id',
        readonly=True,
    )
    readonly_amount = fields.Monetary(
        # string='Payment Amount',
        # required=True
        related='amount',
        readonly=True,
    )

    @api.onchange('deposited_check_ids')
    def onchange_checks(self):
        self.amount = sum(self.deposited_check_ids.mapped('balance'))

    deposited_check_ids = fields.One2many(
        'account.move.line',
        'check_deposit_id',
        string='Deposited Checks',
        readonly=True,
        states={'draft': [('readonly', '=', False)]}
    )
    communication = fields.Char(
        # because onchange function is not called on onchange and we want
        # to clean check number name
        copy=False,
    )

    @api.one
    @api.onchange('check_number', 'checkbook_id')
    # @api.depends('check_number', 'checkbook_id', 'checkbook_id.padding')
    # def _get_name(self):
    def change_check_number(self):
        # TODO make default padding a parameter
        if self.payment_method_code in ['received_third_check', 'issue_check']:
            if not self.check_number:
                communication = False
            else:
                padding = self.checkbook_id and self.checkbook_id.padding or 8
                if len(str(self.check_number)) > padding:
                    padding = len(str(self.check_number))
                communication = _('Check nbr %s') % (
                    '%%0%sd' % padding % self.check_number)
            self.communication = communication

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
    check_number = fields.Integer(
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

    @api.onchange(
        'payment_method_code',
        'check_number',
    )
    @api.constrains(
        'payment_method_code',
        'check_number',
    )
    def check_number_interval(self):
        for rec in self:
            if (
                    rec.payment_method_code == 'issue_check' and
                    rec.checkbook_id and (
                        rec.check_number < rec.checkbook_id.range_from or
                        rec.check_number > rec.checkbook_id.range_to)):
                raise UserError(_(
                    'Check number must be between %s and %s on checkbook '
                    '%s(%s)') % (rec.checkbook_id.name, rec.checkbook_id.id))
        return False

    @api.one
    @api.constrains('check_issue_date', 'check_payment_date')
    @api.onchange('check_issue_date', 'check_payment_date')
    def onchange_date(self):
        if (
                self.check_issue_date and self.check_payment_date and
                self.check_issue_date > self.check_payment_date):
            self.check_payment_date = False
            raise UserError(
                _('Check Payment Date must be greater than Issue Date'))

    @api.one
    @api.onchange('partner_id')
    def onchange_partner_check(self):
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
            vals['check_number'] = self.check_number
            vals['checkbook_id'] = self.checkbook_id.id
            vals['check_issue_date'] = self.check_issue_date
            if self.payment_method_code == 'issue_check':
                vals['check_type'] = 'issue_check'
            else:
                vals['check_type'] = 'third_check'
        return vals

    @api.one
    @api.onchange('checkbook_id')
    def onchange_checkbook(self):
        if self.checkbook_id:
            self.check_number = self.checkbook_id.next_check_number
