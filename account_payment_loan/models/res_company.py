from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    loan_journal_id = fields.Many2one("account.journal")
    loan_account_id = fields.Many2one(
        "account.account",
        help="Account used to identify and record loan receivable lines. Kept independent from "
        "loan_journal_id.default_account_id: a receivable/payable account can't be a journal's default "
        "account (see account.account _check_account_is_bank_journal_bank_account).",
    )
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
