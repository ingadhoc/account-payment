from odoo import models


class AccountBankStatementLine(models.Model):

    _inherit = "account.bank.statement.line"

    def process_reconciliation(self, counterpart_aml_dicts=None,
                               payment_aml_rec=None, new_aml_dicts=None):
        """ Pass reconcilation parameters by context in order to
        capture them in the post() method and be able to get a better
        partner_id/partner_type interpetration
        """
        return super(AccountBankStatementLine, self.with_context(
            counterpart_aml_dicts=counterpart_aml_dicts,
            payment_aml_rec=payment_aml_rec,
            new_aml_dicts=new_aml_dicts,
            )).process_reconciliation(
                counterpart_aml_dicts=counterpart_aml_dicts,
                payment_aml_rec=payment_aml_rec, new_aml_dicts=new_aml_dicts)
