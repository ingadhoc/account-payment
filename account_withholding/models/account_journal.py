# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _enable_withholding_on_cash_journals(self):
        """ Enables withholding payment method
            Called upon module installation via data file.
        """
        inbound_withholding = self.env.ref(
            'account_withholding.account_payment_method_in_withholding')
        outbound_withholding = self.env.ref(
            'account_withholding.account_payment_method_out_withholding')
        domain = [('type', '=', 'cash')]
        force_company_id = self._context.get('force_company_id')
        if force_company_id:
            domain += [('company_id', '=', force_company_id)]
        cash_journals = self.search(domain)
        for cash_journal in cash_journals:
            cash_journal.write({
                'inbound_payment_method_ids': [
                    (4, inbound_withholding.id, None)],
                'outbound_payment_method_ids': [
                    (4, outbound_withholding.id, None)],
            })
