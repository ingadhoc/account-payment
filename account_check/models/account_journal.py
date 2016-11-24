# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    checkbook_ids = fields.One2many(
        'account.checkbook',
        'journal_id',
        'Checkbooks',
    )

    @api.model
    def create(self, vals):
        rec = super(AccountJournal, self).create(vals)
        issue_checks = self.env.ref(
            'account_check.account_payment_method_issue_check')
        if (issue_checks in rec.outbound_payment_method_ids and
                not rec.checkbook_ids):
            rec._create_checkbook()
        return rec

    @api.one
    def _create_checkbook(self):
        """ Create a check sequence for the journal """
        self.checkbook_ids.create({
            'journal_id': self.id,
        })
        # self.check_sequence_id = self.env['ir.sequence'].sudo().create({
        #     'name': self.name + _(" : Check Number Sequence"),
        #     'implementation': 'no_gap',
        #     'padding': 5,
        #     'number_increment': 1,
        #     'company_id': self.company_id.id,
        # })

    @api.model
    def _prepare_liquidity_account(self, name, company, currency_id, type):
        vals = super(AccountJournal, self)._prepare_liquidity_account(
            name, company, currency_id, type)
        print 'self._context', self._context
        print 'name', name
        print 'type', type
        return vals

    @api.model
    def _enable_issue_check_on_bank_journals(self):
        """ Enables issue checks payment method
            Called upon module installation via data file.
        """
        issue_checks = self.env.ref(
            'account_check.account_payment_method_issue_check')
        bank_journals = self.search([('type', '=', 'bank')])
        for bank_journal in bank_journals:
            bank_journal._create_checkbook()
            bank_journal.write({
                'outbound_payment_method_ids': [(4, issue_checks.id, None)],
            })

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