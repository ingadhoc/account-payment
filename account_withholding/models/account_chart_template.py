# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api
import logging
_logger = logging.getLogger(__name__)


class WizardMultiChartsAccounts(models.TransientModel):
    _inherit = 'wizard.multi.charts.accounts'

    @api.multi
    def _create_bank_journals_from_o2m(self, company, acc_template_ref):
        """
        Bank - Cash journals are created with this method
        Inherit this function in order to add checks to cash and bank
        journals. This is because usually will be installed before chart loaded
        and they will be disable by default
        """
        res = super(
            WizardMultiChartsAccounts, self)._create_bank_journals_from_o2m(
            company, acc_template_ref)
        journals = self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'cash'),
        ])
        withholding_method_in = self.env.ref(
            'account_withholding.'
            'account_payment_method_in_withholding')
        withholding_method_out = self.env.ref(
            'account_withholding.'
            'account_payment_method_out_withholding')
        journals.write({
            'inbound_payment_method_ids': [
                (4, withholding_method_in.id, None)],
            'outbound_payment_method_ids': [
                (4, withholding_method_out.id, None)],
        })
        return res
