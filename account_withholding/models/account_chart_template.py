##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models
import logging
_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.Model):
    _inherit = "account.chart.template"

    def _create_bank_journals(self, company, acc_template_ref):
        """
        Bank - Cash journals are created with this method
        Inherit this function in order to add checks to cash and bank
        journals. This is because usually will be installed before chart loaded
        and they will be disable by default
        """

        bank_journals = super(
            AccountChartTemplate, self)._create_bank_journals(
            company, acc_template_ref)

        if company._localization_use_withholdings():
            journal = self.env['account.journal'].with_context(withholding_journal=True).create({
                'name': 'Retenciones',
                'type': 'cash',
                'company_id': company.id,
            })
            bank_journals += journal

            # we dont want this journal to have accounts and we can not inherit
            # to avoid creation, so we delete it
            to_unlink = journal.default_account_id
            journal.default_account_id = False
            to_unlink.unlink()
        return bank_journals
