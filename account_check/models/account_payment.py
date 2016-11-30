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

    _inherit = 'account.payment'
    # _name = 'account.check'
    # _description = 'Account Check'
    # _order = "id desc"
    # _inherit = ['mail.thread']

    # communication = fields.Char(
    #     # because onchange function is not called on onchange and we want
    #     # to clean check number name
    #     copy=False,
    # )
    # TODO tal vez renombrar a check_ids
    deposited_check_ids = fields.Many2many(
        'account.check',
        # 'account.move.line',
        # 'check_deposit_id',
        string='Checks',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', '=', False)]}
    )
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
    check_id = fields.Many2one(
        'account.check',
        string='Check',
        # string='Payment Amount',
        # required=True
        readonly=True,
        copy=False,
    )

# check fields, just to make it easy to load checks without need to create
# them by a m2o record
    # deposited_check_ids = fields.One2many(
    check_name = fields.Char(
        'Check Name',
        # required=True,
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
    )
    check_number = fields.Integer(
        'Check Number',
        # required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False
    )
    check_issue_date = fields.Date(
        'Check Issue Date',
        # required=True,
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
        default=fields.Date.context_today,
    )
    check_payment_date = fields.Date(
        'Check Payment Date',
        readonly=True,
        help="Only if this check is post dated",
        states={'draft': [('readonly', False)]}
    )
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        readonly=True,
        states={'draft': [('readonly', False)]},
        # TODO hacer con un onchange
        # default=_get_checkbook,
    )
    check_subtype = fields.Selection(
        related='checkbook_id.issue_check_subtype',
    )
    check_bank_id = fields.Many2one(
        'res.bank',
        'Check Bank',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]}
    )
    check_owner_vat = fields.Char(
        # TODO rename to Owner VAT
        'Check Owner Vat',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]}
    )
    check_owner_name = fields.Char(
        'Check Owner Name',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]}
    )
    check_type = fields.Char(
        compute='_compute_check_type',
        # this fields is to help with code and view
    )

    @api.multi
    @api.depends('payment_method_code')
    def _compute_check_type(self):
        for rec in self:
            if rec.payment_method_code == 'issue_check':
                rec.check_type = 'issue_check'
            elif rec.payment_method_code in [
                    'received_third_check',
                    'delivered_third_check']:
                rec.check_type = 'third_check'


# on change methods

    # @api.constrains('deposited_check_ids')
    @api.onchange('deposited_check_ids')
    def onchange_checks(self):
        # if self.deposited_check_ids:
        self.amount = sum(self.deposited_check_ids.mapped('amount'))

    # TODo activar
    @api.one
    @api.onchange('check_number', 'checkbook_id')
    def change_check_number(self):
        # TODO make default padding a parameter
        if self.payment_method_code in ['received_third_check']:
            if not self.check_number:
                check_name = False
            else:
                # TODO make optional
                padding = 8
                if len(str(self.check_number)) > padding:
                    padding = len(str(self.check_number))
                # communication = _('Check nbr %s') % (
                check_name = ('%%0%sd' % padding % self.check_number)
                # communication = (
                #     '%%0%sd' % padding % self.check_number)
            self.check_name = check_name

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
        commercial_partner = self.partner_id.commercial_partner_id
        self.check_bank_id = (
            commercial_partner.bank_ids and
            commercial_partner.bank_ids[0].bank_id.id or False)
        self.check_owner_name = commercial_partner.name
        # TODO use document number instead of vat?
        self.check_owner_vat = commercial_partner.vat

    @api.onchange('payment_method_code')
    def _onchange_payment_method_code(self):
        if self.payment_method_code == 'issue_check':
            checkbook = self.env['account.checkbook'].search([
                ('state', '=', 'active'),
                ('journal_id', '=', self.journal_id.id)],
                limit=1)
            self.checkbook_id = checkbook

    @api.onchange('checkbook_id')
    def onchange_checkbook(self):
        if self.checkbook_id:
            self.check_number = self.checkbook_id.next_number


# post methods
    @api.model
    def create(self, vals):
        issue_checks = self.env.ref(
            'account_check.account_payment_method_issue_check')
        if vals['payment_method_id'] == issue_checks.id and vals.get(
                'checkbook_id'):
            checkbook = self.env['account.checkbook'].browse(
                vals['checkbook_id'])
            vals.update({
                # beacause number was readonly we write it here
                'check_number': checkbook.next_number,
                'check_name': checkbook.sequence_id.next_by_id(),
            })
        return super(AccountPayment, self.sudo()).create(vals)

    @api.multi
    def cancel(self):
        res = super(AccountPayment, self).cancel()
        for rec in self:
            rec.do_checks_operations(cancel=True)
            # if rec.check_id:
            #     # rec.check_id._add_operation('cancel')
            #     rec.check_id._del_operation()
            #     rec.check_id.unlink()
            # elif rec.deposited_check_ids:
            #     rec.deposited_check_ids._del_operation()
        return res

    @api.multi
    def create_check(self, check_type, operation, bank):
        self.ensure_one()

        check_vals = {
            'bank_id': bank.id,
            'owner_name': self.check_owner_name,
            'owner_vat': self.check_owner_vat,
            'number': self.check_number,
            'name': self.check_name,
            'checkbook_id': self.checkbook_id.id,
            'issue_date': self.check_issue_date,
            'type': self.check_type,
            'journal_id': self.journal_id.id,
            'amount': self.amount,
            # TODO arreglar que monto va de amount y cual de amount currency
            # 'amount_currency': self.amount,
            'currency_id': self.currency_id.id,
        }
        check = self.env['account.check'].create(check_vals)
        self.check_id = check.id
        check._add_operation(operation, self, self.partner_id)
        return check

    @api.multi
    def do_checks_operations(self, vals=None, cancel=False):
        """
        Check attached .ods file on this module to understand checks workflows
        This method is called from:
        * cancellation of payment to execute delete the right operation and
            unlink check if needed
        * from _get_liquidity_move_line_vals to add check operation and, if
            needded, change payment vals and/or create check and
        """
        self.ensure_one()
        rec = self
        if not rec.check_type:
            # continue
            return vals
        if (
                rec.payment_method_code == 'received_third_check' and
                rec.payment_type == 'inbound' and
                rec.partner_type == 'customer'):
            operation = 'holding'
            if cancel:
                _logger.info('Cancel Receive Check')
                rec.check_id._del_operation(operation)
                rec.check_id.unlink()
                return None

            _logger.info('Receive Check')
            self.create_check('third_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            vals['account_id'] = self.company_id._get_check_account(
                'holding').id
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'cash'):
            operation = 'selled'
            if cancel:
                _logger.info('Cancel Sell Check')
                rec.deposited_check_ids._del_operation(operation)
                return None

            _logger.info('Sell Check')
            rec.deposited_check_ids._add_operation(
                operation, rec, False)
            vals['account_id'] = self.company_id._get_check_account(
                'holding').id
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'bank'):
            operation = 'deposited'
            if cancel:
                _logger.info('Cancel Deposit Check')
                rec.deposited_check_ids._del_operation(operation)
                return None

            _logger.info('Deposit Check')
            rec.deposited_check_ids._add_operation(
                operation, rec, False)
            vals['account_id'] = self.company_id._get_check_account(
                'holding').id
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'outbound' and
                rec.partner_type == 'supplier'):
            operation = 'delivered'
            if cancel:
                _logger.info('Cancel Deliver Check')
                rec.deposited_check_ids._del_operation(operation)
                return None

            _logger.info('Deliver Check')
            rec.deposited_check_ids._add_operation(
                operation, rec, rec.partner_id)
            vals['account_id'] = self.company_id._get_check_account(
                'holding').id
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'outbound' and
                rec.partner_type == 'supplier'):
            operation = 'handed'
            if cancel:
                _logger.info('Cancel Hand Check')
                rec.check_id._del_operation(operation)
                rec.check_id.unlink()
                return None

            _logger.info('Hand Check')
            self.create_check('issue_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            # if check is deferred, change account
            if self.check_subtype == 'deferred':
                vals['account_id'] = self.company_id._get_check_account(
                    'deferred').id
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'cash'):
            operation = 'withdrawed'
            if cancel:
                _logger.info('Cancel Withdrawal Check')
                rec.check_id._del_operation(operation)
                rec.check_id.unlink()
                return None

            _logger.info('Hand Check')
            self.create_check('issue_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            # if check is deferred, change account
            # si retiramos por caja directamente lo sacamos de banco
            # if self.check_subtype == 'deferred':
            #     vals['account_id'] = self.company_id._get_check_account(
            #         'deferred').id
        else:
            raise UserError(_(
                'This operatios is not implemented for checks:\n'
                '* Payment type: %s\n'
                '* Partner type: %s\n'
                '* Payment method: %s\n'
                '* Destination journal: %s\n' % (
                    rec.payment_type,
                    rec.partner_type,
                    rec.payment_method_code,
                    rec.destination_journal_id.type)))
        return vals

    # @api.multi
    # def post(self):
    #     self.do_checks_operations()
    #     return super(AccountPayment, self).post()

    def _get_liquidity_move_line_vals(self, amount):
        vals = super(AccountPayment, self)._get_liquidity_move_line_vals(
            amount)
        vals = self.do_checks_operations(vals=vals)
        # if self.check_type:
        #     vals['date_maturity'] = self.check_payment_date
        #     if self.check_subtype == 'deferred':
        #         deferred_account = self.company_id.deferred_check_account_id
        #         if not deferred_account:
        #             raise UserError(_(
        #                 'No checks deferred account defined for company %s'
        #             ) % self.company_id.name)
        #         vals['account_id'] = deferred_account.id
        #     # vals['check_bank_id'] = self.check_bank_id.id
        #     # vals['check_owner_name'] = self.check_owner_name
        #     # vals['check_owner_vat'] = self.check_owner_vat
        #     # vals['check_number'] = self.check_number
        #     # vals['checkbook_id'] = self.checkbook_id.id
        #     # vals['check_issue_date'] = self.check_issue_date
        #     # if self.payment_method_code == 'issue_check':
        #     #     vals['check_type'] = 'issue_check'
        #     # else:
        #     #     vals['check_type'] = 'third_check'
        return vals

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
    # check_state = fields.Selection([
    #     ('draft', 'Draft'),
    #     ('holding', 'Holding'),
    #     ('deposited', 'Deposited'),
    #     ('handed', 'Handed'),
    #     ('rejected', 'Rejected'),
    #     ('debited', 'Debited'),
    #     ('returned', 'Returned'),
    #     ('changed', 'Changed'),
    #     ('cancel', 'Cancel'),
    # ],
    #     'Check State',
    #     # required=True,
    #     # track_visibility='onchange',
    #     default='draft',
    #     compute='_compute_check_state'
    #     # copy=False,
    # )

    # @api.one
    # def _compute_check_state(self):
    #     state = False
    #     if self.payment_method_code == 'received_third_check':
    #         if self.state == 'draft':
    #             state = 'draft'
    #         elif self.state == 'posted':
    #             state = 'holding'
    #     self.check_state = state
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

    # @api.multi
    # def post(self):
    #     res = super(AccountPayment, self).post()
    #     for rec in self:
    #         if not rec.check_type:
    #             continue
    #         if rec.payment_method_code == 'delivered_third_check':
    #             if not rec.deposited_check_ids:
    #                 raise UserError(_('No checks configured for deposit'))
    #             # liquidity_account = rec.journal_id.default_debit_account_id
    #             # liquidity_line = rec.move_line_ids.filtered(
    #             #     lambda x: x.account_id == liquidity_account)
    #             # rec.deposited_check_ids.write({
    #             #     'deposit_move_line_id': liquidity_line.id})
    #             partner = rec.partner_id.browse()
    #             # if it is a transfer (Deposit) partner is not claned, so we
    #             # clean it here
    #             if rec.payment_type != 'transfer':
    #                 partner = rec.partner_id
    #             rec.deposited_check_ids._add_operation(
    #                 # 'deposited', liquidity_line, liquidity_line.partner_id)
    #                 'deposited', rec, partner)
    #         else:
    #             # liquidity_accounts = (
    #             #     rec.journal_id.default_debit_account_id +
    #             #     rec.journal_id.default_credit_account_id +
    #             #     rec.company_id.deferred_check_account_id)
    #             # liquidity_line = rec.move_line_ids.filtered(
    #             #     lambda x: x.account_id in liquidity_accounts)
    #             if rec.check_type == 'issue_check':
    #                 # TODO tal vez si el cheques es current lo marcamos
    #                 # directamente debitado?
    #                 operation = 'handed'
    #                 bank = rec.journal_id.bank_id
    #             else:
    #                 # third check
    #                 operation = 'holding'
    #                 bank = rec.check_bank_id

    #             check_vals = {
    #                 'bank_id': bank.id,
    #                 'owner_name': rec.check_owner_name,
    #                 'owner_vat': rec.check_owner_vat,
    #                 'number': rec.check_number,
    #                 'name': rec.check_name,
    #                 'checkbook_id': rec.checkbook_id.id,
    #                 'issue_date': rec.check_issue_date,
    #                 # 'move_line_id': liquidity_line.id,
    #                 'type': rec.check_type,
    #                 # new fields because no more related ones on check
    #                 'journal_id': rec.journal_id.id,
    #                 # TODO arreglar que monto va de amount y cual de
    #                 # amount currency
    #                 'amount': rec.amount,
    #                 # 'amount_currency': rec.amount,
    #                 'currency_id': rec.currency_id.id,
    #             }
    #             check = rec.env['account.check'].create(check_vals)
    #             rec.check_id = check.id
    #             check._add_operation(
    #                 # operation, liquidity_line, liquidity_line.partner_id)
    #                 operation, rec, rec.partner_id)
    #     return res
