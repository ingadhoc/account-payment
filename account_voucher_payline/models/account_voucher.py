# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp


class account_voucher(models.Model):

    _inherit = "account.voucher"

    net_amount = fields.Float(
        'Amount',
        digits=dp.get_precision('Account'),
        required=True,
        default=0.0,    # for compatibility with other modules
        readonly=True,
        states={'draft': [('readonly', False)]},
        help='Amount Paid With Journal Method',
    )
    paylines_amount = fields.Float(
        _('Paylines Amount'),
        compute='_get_paylines_amount',
        digits=dp.get_precision('Account'),
        help=_('Amount Paid With Paylines: checks, withholdings, etc.'),
    )
    amount = fields.Float(
        string='Total Amount',
        compute='_get_amount',
        inverse='_set_net_amount',
        help='Total Amount Paid',
        copy=False,
        store=True,
    )
    # we created amount_readonly because we keep amount invisible so
    # it can be setted (if we make amount readonly it wont be setted).
    amount_readonly = fields.Float(
        related='amount',
        string='Total Amount',
        digits=dp.get_precision('Account'),
        readonly=True,
    )
    dummy_journal_id = fields.Many2one(
        related='journal_id',
        readonly=True,
        string='Dummy Journa',
        help='Field used for new api onchange methods over journal',
    )
    reconciled_amount = fields.Float(
        compute='_get_reconciled_amount',
        string='Reconciled Amount',
    )

    @api.one
    @api.depends(
        'line_cr_ids.amount',
        'line_dr_ids.amount',
    )
    def _get_reconciled_amount(self):
        debit = sum(self.line_cr_ids.mapped('amount'))
        credit = sum(self.line_dr_ids.mapped('amount'))
        reconciled_amount = debit - credit
        if self.type == 'payment':
            reconciled_amount = -1 * reconciled_amount
        self.reconciled_amount = reconciled_amount

    @api.one
    @api.depends(
        'net_amount',
        'paylines_amount',
    )
    def _get_amount(self):
        amount = self.paylines_amount + self.net_amount
        self.amount = amount

    @api.one
    def _set_net_amount(self):
        self.net_amount = self.amount - self.paylines_amount

    @api.one
    def _get_paylines_amount(self):
        self.paylines_amount = self.get_paylines_amount()[self.id]

    @api.multi
    def get_paylines_amount(self):
        res = {}
        for voucher in self:
            res[voucher.id] = 0.0
        return res

    @api.model
    def paylines_moves_create(
            self, voucher, move_id, company_currency, current_currency):
        """This function will be inherited by other modules that whant to add
        paylines and whant to make custom accout.move.lines, this function
        returns a total for all the lines created with this method
        """
        paylines_total = 0.0
        # If net amount create first move line (journal line)
        if voucher.net_amount:
            move_line = self.create_first_line(
                voucher, move_id, company_currency, current_currency)
            paylines_total = move_line.debit - move_line.credit
        return paylines_total

    @api.model
    def create_first_line(
            self, voucher, move_id, company_currency, current_currency):
        """Function that creates first move line and return the move line
        created.
        """
        move_lines = self.env['account.move.line']
        name = voucher.name or '/'
        payment_date = voucher.date_due
        amount = voucher.net_amount
        account = voucher.account_id
        partner = voucher.partner_id
        move_line = move_lines.create(
            self.prepare_move_line(
                voucher, amount, move_id, name, company_currency,
                current_currency, payment_date, account, partner)
        )
        return move_line

    @api.model
    def prepare_move_line(
            self, voucher, amount, move_id, name, company_currency,
            current_currency, date_due, account, partner):
        """
        Function that will be use to create first move line and can be used to
        add every payline you add in your custom module.
        """
        debit = credit = 0.0
        if voucher.type in ('purchase', 'payment'):
            credit = self._convert_amount(amount, voucher.id)
        elif voucher.type in ('sale', 'receipt'):
            debit = self._convert_amount(amount, voucher.id)
        if debit < 0:
            credit = -debit
            debit = 0.0
        if credit < 0:
            debit = -credit
            credit = 0.0
        sign = debit - credit < 0 and -1 or 1
        move_line = {
            'name': name,
            'debit': debit,
            'credit': credit,
            'account_id': account.id,
            'partner_id': partner.id,
            'move_id': move_id,
            'journal_id': voucher.journal_id.id,
            'period_id': voucher.period_id.id,
            'currency_id': company_currency != current_currency and current_currency or False,
            'amount_currency': (sign * abs(amount)  # amount < 0 for refunds
                                if company_currency != current_currency else 0.0),
            'date': voucher.date,
            'date_maturity': date_due or False,
        }
        return move_line

    def action_move_line_create(self, cr, uid, ids, context=None):
        '''
        We overwrite this function in order to give the posibility of adding
        paylines. We mark with # CHANGE where we change the code.
        ORIGINAL DESCRIPTION:
        Confirm the vouchers given in ids and create the journal entries for
        each of them
        '''
        if context is None:
            context = {}
        move_pool = self.pool.get('account.move')
        move_line_pool = self.pool.get('account.move.line')
        for voucher in self.browse(cr, uid, ids, context=context):
            local_context = dict(
                context, force_company=voucher.journal_id.company_id.id)
            if voucher.move_id:
                continue
            company_currency = self._get_company_currency(
                cr, uid, voucher.id, context)
            current_currency = self._get_current_currency(
                cr, uid, voucher.id, context)
            # we select the context to use accordingly if it's a multicurrency
            # case or not
            context = self._sel_context(cr, uid, voucher.id, context)
            # But for the operations made by _convert_amount, we always need to
            # give the date in the context
            ctx = context.copy()
            ctx.update({'date': voucher.date})
            # Create the account move record.
            move_id = move_pool.create(cr, uid, self.account_move_get(
                cr, uid, voucher.id, context=context), context=context)
            # Get the name of the account_move just created
            name = move_pool.browse(cr, uid, move_id, context=context).name

            # CHANGE
            # COMENTADO
            # Create the first line of the voucher
            # move_line_id = move_line_pool.create(cr, uid, self.first_move_line_get(
            #     cr, uid, voucher.id, move_id, company_currency, current_currency, local_context), local_context)
            # move_line_brw = move_line_pool.browse(
            #     cr, uid, move_line_id, context=context)
            # line_total = move_line_brw.debit - move_line_brw.credit
            # END COMENTADO
            # AGREGADO
            # if voucher.type in ('payment', 'receipt'):
            # Create move line for echa payline
            # for payline in voucher.payline_ids:
            line_total = self.paylines_moves_create(
                cr, uid, voucher, move_id, company_currency,
                current_currency, context)
            # END AGREGADO
            # END CHANGE
            rec_list_ids = []
            if voucher.type == 'sale':
                line_total = line_total - \
                    self._convert_amount(
                        cr, uid, voucher.tax_amount, voucher.id, context=ctx)
            elif voucher.type == 'purchase':
                line_total = line_total + \
                    self._convert_amount(
                        cr, uid, voucher.tax_amount, voucher.id, context=ctx)
            # Create one move line per voucher line where amount is not 0.0
            line_total, rec_list_ids = self.voucher_move_line_create(
                cr, uid, voucher.id, line_total, move_id, company_currency, current_currency, context)

            # Create the writeoff line if needed
            ml_writeoff = self.writeoff_move_line_get(
                cr, uid, voucher.id, line_total, move_id, name, company_currency, current_currency, local_context)
            if ml_writeoff:
                move_line_pool.create(cr, uid, ml_writeoff, local_context)
            # We post the voucher.
            self.write(cr, uid, [voucher.id], {
                'move_id': move_id,
                'state': 'posted',
                'number': name,
            })
            # CHANGE
            # no matter journal selection, we post the entry
            move_pool.post(cr, uid, [move_id], context={})
            # if voucher.journal_id.entry_posted:
            # move_pool.post(cr, uid, [move_id], context={})
            # We automatically reconcile the account move lines.
            reconcile = False
            for rec_ids in rec_list_ids:
                if len(rec_ids) >= 2:
                    reconcile = move_line_pool.reconcile_partial(
                        cr, uid, rec_ids, writeoff_acc_id=voucher.writeoff_acc_id.id, writeoff_period_id=voucher.period_id.id, writeoff_journal_id=voucher.journal_id.id)
        return True
