# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import fields, models, _, api
from openerp.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountCheckOperation(models.Model):

    _name = 'account.check.operation'
    _rec_name = 'operation'
    _order = 'create_date desc'

    # we use create_date
    # date = fields.Datetime(
    #     # default=fields.Date.context_today,
    #     default=lambda self: fields.Datetime.now(),
    #     required=True,
    # )
    check_id = fields.Many2one(
        'account.check',
        required=True,
        ondelete='cascade'
    )
    operation = fields.Selection([
        ('draft', 'Draft'),
        ('holding', 'Holding'),
        ('deposited', 'Deposited'),
        ('endorsed', 'Endorsed'),
        ('handed', 'Handed'),
        ('rejected', 'Rejected'),
        ('debited', 'Debited'),
        ('returned', 'Returned'),
        ('changed', 'Changed'),
        ('cancel', 'Cancel'),
    ],
        required=True,
    )
    move_line_id = fields.Many2one(
        'account.move.line',
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner',
    )


class AccountCheck(models.Model):

    _name = 'account.check'
    _description = 'Account Check'
    _order = "id desc"
    _inherit = ['mail.thread']

    operation_ids = fields.One2many(
        'account.check.operation',
        'check_id',
    )
    name = fields.Char(
        required=True,
        readonly=True,
        copy=False
    )
    number = fields.Integer(
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False
    )
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        readonly=True,
        states={'draft': [('readonly', False)]},
        # default=_get_checkbook,
    )
    type = fields.Selection(
        [('issue_check', 'Issue Check'), ('third_check', 'Third Check')],
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('holding', 'Holding'),
        ('deposited', 'Deposited'),
        ('endorsed', 'Endorsed'),
        ('handed', 'Handed'),
        ('rejected', 'Rejected'),
        ('debited', 'Debited'),
        ('returned', 'Returned'),
        ('changed', 'Changed'),
        ('cancel', 'Cancel'),
    ],
        required=True,
        track_visibility='onchange',
        default='draft',
        copy=False,
        compute='_compute_state',
        # search='_search_state',
        # TODO enable store, se complico, ver search o probar si un related
        # resuelve
        # store=True,
    )
    issue_date = fields.Date(
        'Issue Date',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=fields.Date.context_today,
    )
    owner_vat = fields.Char(
        'Owner Vat',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    owner_name = fields.Char(
        'Owner Name',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    bank_id = fields.Many2one(
        'res.bank', 'Bank',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )

# move.line fields
    move_line_id = fields.Many2one(
        'account.move.line',
        'Check Entry Line',
        readonly=True,
        copy=False
    )
    deposit_move_line_id = fields.Many2one(
        'account.move.line',
        'Deposit Journal Item',
        readonly=True,
        copy=False
    )
# rejection fields
    # supplier_reject_debit_note_id = fields.Many2one(
    #     'account.invoice',
    #     'Supplier Reject Debit Note',
    #     readonly=True,
    #     copy=False,
    # )
    # customer_reject_debit_note_id = fields.Many2one(
    #     'account.invoice',
    #     'Customer Reject Debit Note',
    #     readonly=True,
    #     copy=False
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
    # deposit_account_move_id = fields.Many2one(
    #     'account.move',
    #     'Deposit Account Move',
    #     readonly=True,
    #     copy=False
    # )
    # return_account_move_id = fields.Many2one(
    #     'account.move',
    #     'Return Account Move',
    #     readonly=True,
    #     copy=False
    # )

# Related fields
    # amount = fields.Monetary(
    #     'Amount',
    #     currency_field='currency_id',
    #     required=True,
    #     readonly=True,
    #     states={'draft': [('readonly', False)]},
    # )
    # company_currency_amount = fields.Monetary(
    #     'Company Currency Amount',
    #     currency_field='company_currency_id',
    #     readonly=True,
    #     help='This value is only set for those checks that has a different '
    #     'currency than the company one.'
    # )

# ex campos related
    amount = fields.Monetary(
        # related='move_line_id.balance',
        currency_field='company_currency_id'
    )
    amount_currency = fields.Monetary(
        # related='move_line_id.amount_currency',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        # related='move_line_id.currency_id',
    )
    payment_date = fields.Date(
        # related='move_line_id.date_maturity',
        # store=True,
        # readonly=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        # related='move_line_id.journal_id',
        # store=True,
        # readonly=True,
    )
    company_id = fields.Many2one(
        related='journal_id.company_id'
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
    )

# TODO VER SI BORRAMOS< CAMPOS VIEJOS RELATED< AHORA LOS ESTOREAMOS
    # amount = fields.Monetary(
    #     related='move_line_id.balance',
    # )
    # amount_currency = fields.Monetary(
    #     related='move_line_id.amount_currency',
    # )
    # company_currency_id = fields.Many2one(
    #     related='move_line_id.company_currency_id',
    # )
    # currency_id = fields.Many2one(
    #     related='move_line_id.currency_id',
    # )
    # payment_date = fields.Date(
    #     related='move_line_id.date_maturity',
    #     store=True,
    #     readonly=True,
    # )
    # journal_id = fields.Many2one(
    #     related='move_line_id.journal_id',
    #     store=True,
    #     readonly=True,
    # )

    # @api.model
    # def _get_checkbook(self):
    #     journal_id = self._context.get('default_journal_id', False)
    #     payment_subtype = self._context.get('default_type', False)
    #     if journal_id and payment_subtype == 'issue_check':
    #         checkbooks = self.env['account.checkbook'].search(
    #             [('state', '=', 'active'), ('journal_id', '=', journal_id)])
    #         return checkbooks and checkbooks[0] or False

    # @api.one
    # @api.depends('number', 'checkbook_id', 'checkbook_id.padding')
    # def _get_name(self):
    #     padding = self.checkbook_id and self.checkbook_id.padding or 8
    #     if len(str(self.number)) > padding:
    #         padding = len(str(self.number))
    #     self.name = '%%0%sd' % padding % self.number

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
    # currency_id = fields.Many2one(
    #     'res.currency',
    #     string='Currency',
    #     readonly=True,
    #     related='voucher_id.journal_id.currency',
    # )
    # deposit_date = fields.Date(
    #     related='deposit_account_move_id.date',
    #     store=True,
    #     string='Fecha de Depósito',
    # )
    # account move of return

    @api.multi
    @api.constrains('issue_date', 'payment_date')
    @api.onchange('issue_date', 'payment_date')
    def onchange_date(self):
        for rec in self:
            if (
                    rec.issue_date and rec.payment_date and
                    rec.issue_date > rec.payment_date):
                raise UserError(
                    _('Check Payment Date must be greater than Issue Date'))

    @api.multi
    @api.constrains(
        'type',
        'number',
    )
    def issue_number_interval(self):
        for rec in self:
            # if not range, then we dont check it
            if rec.type == 'issue_check' and rec.checkbook_id.range_to:
                if rec.number > rec.checkbook_id.range_to:
                    raise UserError(_(
                        "Check number can't be greater than %s on checkbook %s"
                    ) % (rec.checkbook_id.range_to, rec.checkbook_id.name))
                elif rec.number == rec.checkbook_id.range_to:
                    rec.checkbook_id.state = 'used'
        return False

    @api.multi
    @api.constrains(
        'type',
        'owner_name',
        'bank_id',
        # 'check_number'
    )
    def _check_unique(self):
        for rec in self:
            if rec.type == 'issue_check':
                same_checks = self.search([
                    ('checkbook_id', '=', rec.checkbook_id.id),
                    ('type', '=', rec.type),
                    ('number', '=', rec.number),
                ])
                same_checks -= self
                if same_checks:
                    raise ValidationError(_(
                        'Check Number must be unique per Checkbook!\n'
                        '* Check ids: %s') % (
                        same_checks.ids))
            elif self.type == 'third_check':
                same_checks = self.search([
                    ('bank_id', '=', rec.bank_id.id),
                    ('owner_name', '=', rec.owner_name),
                    ('type', '=', rec.type),
                    ('number', '=', rec.number),
                ])
                same_checks -= self
                if same_checks:
                    raise ValidationError(_(
                        'Check Number must be unique per Owner and Bank!\n'
                        '* Check ids: %s') % (
                        same_checks.ids))
        return True

    @api.multi
    def _add_operation(self, operation, move_line=None, partner=None):
        for rec in self:
            rec.operation_ids.create({
                'operation': operation,
                'check_id': rec.id,
                'move_line_id': move_line and move_line.id or False,
                'partner_id': partner and partner.id or False,
            })

    # @api.model
    # def _search_state(self, operator, value):
        
    #     # if operator == '=' and operand:
    #     #     return [('needaction_partner_ids', 'in', self.env.user.partner_id.id)]
    #     return [('needaction_partner_ids', 'not in', self.env.user.partner_id.id)]

    @api.multi
    @api.depends(
        'operation_ids.operation',
        'operation_ids.create_date',
        # 'operation_ids',
        # 'operation_ids.date',
    )
    def _compute_state(self):
        # TODO tal ves podemos hacer que los cheques partan del "handed_move_line_id"
        # o algo por el estilo, entocnes los estados serian mas aprecidos para ambos
        # tipos de cheques
        for rec in self:
            print 'aaaaaaa'
            rec.state = (
                rec.operation_ids and
                rec.operation_ids[0].operation or 'draft')

# TODO borrar, funcion vieja pa computar estado
    # @api.multi
    # @api.depends(
    #     'type',
    #     'move_line_id',
    #     'deposit_move_line_id',
    # )
    # def _compute_state(self):
    #     # TODO tal ves podemos hacer que los cheques partan del "handed_move_line_id"
    #     # o algo por el estilo, entocnes los estados serian mas aprecidos para ambos
    #     # tipos de cheques
    #     for rec in self:
    #         state = 'draft'
    #         if rec.type == 'third_check':
    #             if rec.deposit_move_line_id:
    #                 if rec.deposit_move_line_id.partner_id:
    #                     state = 'endorsed'
    #                 else:
    #                     state = 'deposited'
    #             elif rec.move_line_id:
    #                 state = 'holding'
    #         elif rec.type == 'issue_check':
    #             if rec.move_line_id:
    #                 state = 'handed'
    #         else:
    #             raise ValidationError(_(
    #                 'Check %s is not implemented!') % rec.type)
    #         # if rec.supplier_reject_debit_note_id:
    #         #     state = 'rejected'
    #         # elif rec.replacing_check_id:
    #         #     state = 'replaced'
    #         # elif rec.deposit_account_move_id:
    #         #     state = 'debited'
    #         # elif rec.replacing_check_id:
    #         #     state = 'holding'
    #         #     state = 'handed'
    #         #     state = 'debited'
    #         #     state = 'returned'
    #         #     state = 'changed'
    #         #     state = 'cancel'
    #         # elif rec.deposit_account_move_id:
    #         # elif rec.return_account_move_id:
    #         rec.state = state

# si volvemos a activar la constraint entonces ver que cuando cancelamos pago
# se permita borrar, podriamos generar una operacacion de cancelar que lo vuelva
# a borrador o
    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise ValidationError(
                    _('The Check must be in draft state for unlink !'))
        return super(AccountCheck, self).unlink()

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
