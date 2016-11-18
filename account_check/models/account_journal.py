# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    checkbook_ids = fields.One2many(
        'account.checkbook',
        'journal_id',
        'Checkbooks',
    )

    # @api.model
    # def create(self, vals):
    #     journal = super(AccountJournal, self.with_context(vals=vals)).create(vals)
    #     default_account = vals.get('default_debit_account_id') or vals.get('default_credit_account_id')
    #     if not default_account and 
    #     return journal

    # @api.constrains('')
    # def create(self, vals):
    #     if '' in 

    @api.one
    # @api.constrains()
    def check_checks_journal(self):
        # TODO add constrains
        # if self.default_debit_account_id
        return True

    @api.model
    def _prepare_liquidity_account(self, name, company, currency_id, type):
        vals = super(AccountJournal, self)._prepare_liquidity_account(
            name, company, currency_id, type)
        print 'self._context', self._context
        print 'name', name
        print 'type', type
        return vals

    # @api.model
    # def _get_payment_subtype(self):
    #     selection = super(account_journal, self)._get_payment_subtype()
    #     selection.append(('issue_check', _('Issue Check')))
    #     selection.append(('third_check', _('Third Check')))
    #     # same functionality as checks, no need to have both for now
    #     # selection.append(('promissory', _('Promissory Note')))
    #     return selection

    # @api.model
    # def _enable_checks_on_bank_journals(self):
    #     """
    #     Enables check printing payment method and add a check sequence on
    #     bank journals.
    #     Called upon module installation via data file.
    #     """
    #     check_printing = self.env.ref(
    #         'account_check.account_payment_method_check')
    #     bank_journals = self.search([('type', '=', 'bank')])
    #     for bank_journal in bank_journals:
    #         # bank_journal._create_check_sequence()
    #         bank_journal.write({
    #             'outbound_payment_method_ids': [(4, check_printing.id, None)],
    #         })