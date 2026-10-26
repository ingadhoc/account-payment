from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    loan_journal_id = fields.Many2one("account.journal")
    late_payment_interest = fields.Float(
        help="Monthly interest rate for late payments, expressed as a percentage (e.g., 0.10 for 10%). "
        "This would be prorated to a daily interest rate of 1/30 of the monthly rate."
    )
    account_late_payment_interest = fields.Many2one(
        "account.account",
        help="Account used to record late payment interest charges.",
    )
    account_loan_extra_charges = fields.Many2one(
        "account.account",
        help="Account used to record extra charges related to loans.",
    )
    loan_terms = fields.Html(string=" Loan Default Terms and Conditions", translate=True)

    def _set_loan_settings_from_root(self):
        """Branches use the loan journal and accounts of their root company, the same way account
        copies the default accounts of the root when the chart is loaded on a branch."""
        for company in self:
            for fname in ("loan_journal_id", "account_late_payment_interest", "account_loan_extra_charges"):
                company[fname] = company[fname] or company.root_id[fname]
