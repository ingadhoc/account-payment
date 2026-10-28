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

    def _get_loan_setting(self, fname):
        """Loan setting of the closest company in the hierarchy that has it set, so branches use the one of
        their parent company unless they set their own."""
        self.ensure_one()
        return next((company[fname] for company in reversed(self.parent_ids) if company[fname]), self[fname])
