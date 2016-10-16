# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################


class account_journal(models.Model):
    _inherit = 'account.journal'

    # checkbook_ids = fields.One2many(
    #     'account.checkbook',
    #     'journal_id',
    #     'Checkbooks',
    # )

    @api.model
    def _get_payment_subtype(self):
        selection = super(account_journal, self)._get_payment_subtype()
        selection.append(('issue_check', _('Issue Check')))
        selection.append(('third_check', _('Third Check')))
        # same functionality as checks, no need to have both for now
        # selection.append(('promissory', _('Promissory Note')))
        return selection

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
