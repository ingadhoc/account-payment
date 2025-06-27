from odoo import _, models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template(model="account.account")
    def _get_personal_loan_account_account(self, template_code):
        return {
            "account_loan_account": {
                "name": _("Account Receivable Loan"),
                "code": "loan",
                "account_type": "asset_receivable",
                "reconcile": True,
            },
            "account_loan_interest_account": {
                "name": _("Account Interest Loan"),
                "code": "LOI",
                "account_type": "income_other",
            },
            "account_loan_extra_charges": {
                "name": _("Account Extra Charges Loan"),
                "code": "LOE",
                "account_type": "income_other",
            },
            "account_loan_round": {
                "name": _("Rounding"),
                "code": "LOR",
                "account_type": "income_other",
            },
        }

    @template(model="account.journal")
    def _get_personal_loan_journal(self, template_code):
        return {
            "account_loan_journal": {
                "name": _("Personal Loans"),
                "type": "general",
                "code": "LOA",
            },
        }

    def _post_load_data(self, template_code, company, template_data):
        def get_first_parent(company):
            if company.parent_id:
                return get_first_parent(company.parent_id)
            return company

        super()._post_load_data(template_code, company, template_data)
        company = get_first_parent(company or self.env.company)

        account_loan_journal_id = self.env.ref(f"account.{company.id}_account_loan_journal")
        account_loan_journal_id.default_account_id = self.env.ref(f"account.{company.id}_account_loan_account").id

        company.loan_journal_id = account_loan_journal_id.id
        company.account_late_payment_interest = self.env.ref(f"account.{company.id}_account_loan_interest_account").id
        company.account_loan_extra_charges = self.env.ref(f"account.{company.id}_account_loan_extra_charges").id
