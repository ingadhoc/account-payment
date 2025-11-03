from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    loan_journal_id = fields.Many2one(
        related="company_id.loan_journal_id",
        readonly=False,
        help="Journal to be used for registering loan transactions.",
    )

    late_payment_interest = fields.Float(
        related="company_id.late_payment_interest",
        readonly=False,
        help="Monthly interest rate for late payments, expressed as a percentage (e.g., 0.10 for 10%). "
        "This would be prorated to a daily interest rate of 1/30 of the monthly rate.",
    )

    account_late_payment_interest = fields.Many2one(
        related="company_id.account_late_payment_interest",
        readonly=False,
        help="Account used to record income from late payment interests.",
    )

    account_loan_extra_charges = fields.Many2one(
        related="company_id.account_loan_extra_charges",
        readonly=False,
        help="Account used to record additional charges related to loan operations.",
    )
    use_loan_terms = fields.Boolean(
        string="Default Loan Terms & Conditions",
        config_parameter="account.use_loan_terms",
    )
    loan_terms = fields.Html(related="company_id.loan_terms", string="Loan Terms & Conditions", readonly=False)
