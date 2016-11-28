# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api


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
        checkbook = self.checkbook_ids.create({
            'journal_id': self.id,
        })
        checkbook.state = 'active'

    @api.model
    def _prepare_liquidity_account(self, name, company, currency_id, type):
        vals = super(AccountJournal, self)._prepare_liquidity_account(
            name, company, currency_id, type)
        return vals

    @api.model
    def _enable_issue_check_on_bank_journals(self):
        """ Enables issue checks payment method
            Called upon module installation via data file.
        """
        issue_checks = self.env.ref(
            'account_check.account_payment_method_issue_check')
        domain = [('type', '=', 'bank')]
        force_company_id = self._context.get('force_company_id')
        if force_company_id:
            domain += [('company_id', '=', force_company_id)]
        bank_journals = self.search(domain)
        for bank_journal in bank_journals:
            bank_journal._create_checkbook()
            bank_journal.write({
                'outbound_payment_method_ids': [(4, issue_checks.id, None)],
            })

    @api.model
    def _enable_third_check_on_cash_journals(self):
        """ Enables issue checks payment method
            Called upon module installation via data file.
        """
        received_third_check = self.env.ref(
            'account_check.account_payment_method_received_third_check')
        delivered_third_check = self.env.ref(
            'account_check.account_payment_method_delivered_third_check')
        domain = [('type', '=', 'cash')]
        force_company_id = self._context.get('force_company_id')
        if force_company_id:
            domain += [('company_id', '=', force_company_id)]
        cash_journals = self.search(domain)
        for cash_journal in cash_journals:
            cash_journal.write({
                'inbound_payment_method_ids': [
                    (4, received_third_check.id, None)],
                'outbound_payment_method_ids': [
                    (4, delivered_third_check.id, None)],
            })
