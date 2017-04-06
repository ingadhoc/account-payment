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

    check_ids = fields.Many2many(
        'account.check',
        string='Checks',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', '=', False)]}
    )
    # only for v8 comatibility where more than one check could be received
    # or issued
    check_ids_copy = fields.Many2many(
        related='check_ids',
        readonly=True,
    )
    readonly_currency_id = fields.Many2one(
        related='currency_id',
        readonly=True,
    )
    readonly_amount = fields.Monetary(
        related='amount',
        readonly=True,
    )
    # we add this field for better usability on issue checks and received
    # checks. We keep m2m field for backward compatibility where we allow to
    # use more than one check per payment
    check_id = fields.Many2one(
        'account.check',
        compute='_compute_check',
        string='Check',
    )

    @api.multi
    @api.depends('check_ids')
    def _compute_check(self):
        for rec in self:
            # we only show checks for issue checks or received thid checks
            # if len of checks is 1
            if rec.payment_method_code in (
                    'received_third_check',
                    'issue_check',) and len(rec.check_ids) == 1:
                rec.check_id = rec.check_ids[0].id

# check fields, just to make it easy to load checks without need to create
# them by a m2o record
    check_name = fields.Char(
        'Check Name',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
    )
    check_number = fields.Integer(
        'Check Number',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False
    )
    check_issue_date = fields.Date(
        'Check Issue Date',
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
    )
    check_subtype = fields.Selection(
        related='checkbook_id.issue_check_subtype',
        readonly=True,
    )
    check_bank_id = fields.Many2one(
        'res.bank',
        'Check Bank',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]}
    )
    check_owner_vat = fields.Char(
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
    # this fields is to help with code and view
    check_type = fields.Char(
        compute='_compute_check_type',
    )
    checkbook_block_manual_number = fields.Boolean(
        related='checkbook_id.block_manual_number',
    )
    check_number_readonly = fields.Integer(
        related='check_number',
        readonly=True,
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

    # @api.constrains('check_ids')
    @api.onchange('check_ids', 'payment_method_code')
    def onchange_checks(self):
        # we only overwrite if payment method is delivered
        if self.payment_method_code == 'delivered_third_check':
            self.amount = sum(self.check_ids.mapped('amount'))

    # TODo activar
    @api.one
    @api.onchange('check_number')
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
            self.check_name = check_name
        elif self.payment_method_code in ['issue_check']:
            if not self.check_number:
                check_name = False
            else:
                sequence = self.checkbook_id.sequence_id
                if self.check_number != sequence.number_next_actual:
                    sequence.write({'number_next_actual': self.check_number})
                check_name = self.checkbook_id.sequence_id.next_by_id()
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
        elif self.checkbook_id:
            # TODO ver si interesa implementar volver atras numeracion
            self.checkbook_id = False

    @api.onchange('checkbook_id')
    def onchange_checkbook(self):
        if self.checkbook_id:
            self.check_number = self.checkbook_id.next_number


# post methods
    @api.multi
    def cancel(self):
        res = super(AccountPayment, self).cancel()
        for rec in self:
            rec.do_checks_operations(cancel=True)
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
            'payment_date': self.check_payment_date,
            # TODO arreglar que monto va de amount y cual de amount currency
            # 'amount_currency': self.amount,
            'currency_id': self.currency_id.id,
        }
        check = self.env['account.check'].create(check_vals)
        self.check_ids = [(4, check.id, False)]
        check._add_operation(
            operation, self, self.partner_id, date=self.payment_date)
        return check

    @api.multi
    def get_third_check_account(self):
        """
        For third checks, if we use a journal only for third checks, we use
        accounts on journal, if not we use company account
        """
        self.ensure_one()
        if self.payment_type in ('outbound', 'transfer'):
            account = self.journal_id.default_debit_account_id
            methods_field = 'outbound_payment_method_ids'
        else:
            account = self.journal_id.default_credit_account_id
            methods_field = 'inbound_payment_method_ids'
        if len(self.journal_id[methods_field]) > 1 or not account:
            account = self.company_id._get_check_account('holding')
        return account

    @api.multi
    def do_checks_operations(self, vals=None, cancel=False):
        """
        Check attached .ods file on this module to understand checks workflows
        This method is called from:
        * cancellation of payment to execute delete the right operation and
            unlink check if needed
        * from _get_liquidity_move_line_vals to add check operation and, if
            needded, change payment vals and/or create check and
        TODO si queremos todos los del operation podriamos moverlos afuera y
        simplificarlo ya que es el mismo en casi todos
        Tambien podemos simplficiar las distintas opciones y como se recorren
        los if
        """
        self.ensure_one()
        rec = self
        if not rec.check_type:
            # continue
            return vals
        if (
                rec.payment_method_code == 'received_third_check' and
                rec.payment_type == 'inbound'
                # el chequeo de partner type no seria necesario
                # un proveedor nos podria devolver plata con un cheque
                # and rec.partner_type == 'customer'
        ):
            operation = 'holding'
            if cancel:
                _logger.info('Cancel Receive Check')
                rec.check_ids._del_operation(self)
                rec.check_ids.unlink()
                return None

            _logger.info('Receive Check')
            self.create_check('third_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            vals['account_id'] = self.get_third_check_account().id
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'transfer'):
            # si el cheque es entregado en una transferencia tenemos tres
            # opciones
            # TODO we should make this method selectable for transfers
            inbound_method = (
                rec.destination_journal_id.inbound_payment_method_ids)
            # si un solo inbound method y es received third check
            # entonces consideramos que se esta moviendo el cheque de un diario
            # al otro
            if len(inbound_method) == 1 and (
                    inbound_method.code == 'received_third_check'):
                if cancel:
                    _logger.info('Cancel Transfer Check')
                    for check in rec.check_ids:
                        check._del_operation(self)
                        check._del_operation(self)
                        receive_op = check._get_operation('holding')
                        if receive_op.origin._name == 'account.payment':
                            check.journal_id = receive_op.origin.journal_id.id
                    return None

                _logger.info('Transfer Check')
                rec.check_ids._add_operation(
                    'transfered', rec, False, date=rec.payment_date)
                rec.check_ids._add_operation(
                    'holding', rec, False, date=rec.payment_date)
                rec.check_ids.write({
                    'journal_id': rec.destination_journal_id.id})
                vals['account_id'] = self.get_third_check_account().id
            elif rec.destination_journal_id.type == 'cash':
                if cancel:
                    _logger.info('Cancel Sell Check')
                    rec.check_ids._del_operation(self)
                    return None

                _logger.info('Sell Check')
                rec.check_ids._add_operation(
                    'selled', rec, False, date=rec.payment_date)
                vals['account_id'] = self.get_third_check_account().id
            # bank
            else:
                if cancel:
                    _logger.info('Cancel Deposit Check')
                    rec.check_ids._del_operation(self)
                    return None

                _logger.info('Deposit Check')
                rec.check_ids._add_operation(
                    'deposited', rec, False, date=rec.payment_date)
                vals['account_id'] = self.get_third_check_account().id
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'outbound'
                # el chequeo del partner type no es necesario
                # podriamos entregarlo a un cliente
                # and rec.partner_type == 'supplier'
        ):
            if cancel:
                _logger.info('Cancel Deliver Check')
                rec.check_ids._del_operation(self)
                return None

            _logger.info('Deliver Check')
            rec.check_ids._add_operation(
                'delivered', rec, rec.partner_id, date=rec.payment_date)
            vals['account_id'] = self.get_third_check_account().id
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'outbound'
                # el chequeo del partner type no es necesario
                # podriamos entregarlo a un cliente
                # and rec.partner_type == 'supplier'
        ):
            if cancel:
                _logger.info('Cancel Hand Check')
                rec.check_ids._del_operation(self)
                rec.check_ids.unlink()
                return None

            _logger.info('Hand Check')
            self.create_check('issue_check', 'handed', self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            # if check is deferred, change account
            if self.check_subtype == 'deferred':
                vals['account_id'] = self.company_id._get_check_account(
                    'deferred').id
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'cash'):
            if cancel:
                _logger.info('Cancel Withdrawal Check')
                rec.check_ids._del_operation(self)
                rec.check_ids.unlink()
                return None

            _logger.info('Hand Check')
            self.create_check('issue_check', 'withdrawed', self.check_bank_id)
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

    def _get_liquidity_move_line_vals(self, amount):
        vals = super(AccountPayment, self)._get_liquidity_move_line_vals(
            amount)
        vals = self.do_checks_operations(vals=vals)
        return vals
