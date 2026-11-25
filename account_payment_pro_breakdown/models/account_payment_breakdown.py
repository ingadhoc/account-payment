from odoo import api, fields, models


class AccountPaymentBreakdown(models.Model):
    _name = "account.payment.breakdown"
    _description = "Amount of a payment allocated to a debt"
    _order = "payment_id, id"

    payment_id = fields.Many2one(
        "account.payment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    move_line_id = fields.Many2one(
        "account.move.line",
        string="Debt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    move_id = fields.Many2one(related="move_line_id.move_id")
    date_maturity = fields.Date(related="move_line_id.date_maturity")
    # In the counterpart currency, the one of the debts: the counterpart lines are built and reconciled in it.
    currency_id = fields.Many2one(related="payment_id.counterpart_currency_id")
    company_id = fields.Many2one(related="payment_id.company_id", store=True)
    amount_residual = fields.Monetary(compute="_compute_amount_residual", string="Amount Due")
    amount = fields.Monetary(currency_field="currency_id", required=True)

    _unique_debt_per_payment = models.Constraint(
        "UNIQUE(payment_id, move_line_id)",
        "A debt can only appear once in the breakdown of a payment.",
    )
    _positive_amount = models.Constraint(
        "CHECK(amount > 0)",
        "The amount allocated to a debt must be positive.",
    )

    @api.model
    def _get_debt_residual(self, debt, currency):
        """What is left to pay of the debt, in the breakdown currency and always positive."""
        residual = debt.amount_residual if currency == debt.company_currency_id else debt.amount_residual_currency
        return abs(residual)

    @api.depends("move_line_id", "currency_id")
    def _compute_amount_residual(self):
        for line in self:
            line.amount_residual = self._get_debt_residual(line.move_line_id, line.currency_id)
