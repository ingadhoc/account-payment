from odoo import fields, models


class AccountCard(models.Model):
    _inherit = "account.card"

    is_loan = fields.Boolean()
    loan_due_method = fields.Selection(
        selection=[
            ("create_day", "every month on the same day it was created "),
            ("next_day_number", "every month on the same day number "),
        ],
    )
    due_day = fields.Integer()
