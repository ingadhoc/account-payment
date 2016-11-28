# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, fields
import logging
_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.Model):
    _inherit = 'account.chart.template'

    @api.model
    def _prepare_all_journals(
            self, acc_template_ref, company, journals_dict=None):
        """
        Inherit this function in order to add checks to cash and bank
        journals. This is because usually will be installed before chart loaded
        and they will be disable by default
        """
        journal_data = super(
            AccountChartTemplate, self)._prepare_all_journals(
            acc_template_ref, company, journals_dict)
        for vals_journal in journal_data:
            if vals_journal['type'] == 'cash':
                withholding_method_in = self.env.ref(
                    'account_check.'
                    'account_payment_method_in_withholding')
                withholding_method_out = self.env.ref(
                    'account_check.'
                    'account_payment_method_out_withholding')
                vals_journal['inbound_payment_method_ids'] = [
                    (4, withholding_method_in.id, None)]
                vals_journal['outbound_payment_method_ids'] = [
                    (4, withholding_method_out.id, None)]
        return journal_data
