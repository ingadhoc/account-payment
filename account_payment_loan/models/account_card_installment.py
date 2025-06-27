from odoo import fields, models


class AccountCardInstallment(models.Model):
    _inherit = "account.card.installment"

    is_loan = fields.Boolean(
        related="card_id.is_loan",
        readonly=False,
    )
