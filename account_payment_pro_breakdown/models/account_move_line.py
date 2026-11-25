from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    breakdown_debt_line_id = fields.Many2one(
        "account.move.line",
        string="Breakdown Debt",
        copy=False,
        index="btree_not_null",
        help="On a counterpart line of a broken down payment, the debt this part is reconciled with.",
    )
