from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPaymentBreakdownWizard(models.TransientModel):
    _name = "account.payment.breakdown.wizard"
    _description = "Break down a payment between its debts"

    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    currency_id = fields.Many2one(related="payment_id.counterpart_currency_id")
    total_amount = fields.Monetary(related="payment_id.counterpart_currency_amount", string="Payment Amount")
    line_ids = fields.One2many("account.payment.breakdown.wizard.line", "wizard_id")
    allocated_amount = fields.Monetary(compute="_compute_amounts")
    difference = fields.Monetary(compute="_compute_amounts")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        payment = self.env["account.payment"].browse(res.get("payment_id"))
        if payment and "line_ids" in fields_list:
            current = {breakdown.move_line_id: breakdown.amount for breakdown in payment.breakdown_ids}
            res["line_ids"] = [
                fields.Command.create({"move_line_id": line.id, "amount": current.get(line, 0.0)})
                for line in payment.to_pay_move_line_ids.sorted(lambda line: (line.date_maturity or line.date, line.id))
            ]
        return res

    @api.depends("total_amount", "line_ids.amount")
    def _compute_amounts(self):
        for wizard in self:
            wizard.allocated_amount = sum(wizard.line_ids.mapped("amount"))
            wizard.difference = wizard.total_amount - wizard.allocated_amount

    def action_confirm(self):
        self.ensure_one()
        if not self.currency_id.is_zero(self.difference):
            raise UserError(
                _(
                    "The amounts must add up to the payment amount. Difference: %(difference)s",
                    difference=self.currency_id.format(self.difference),
                )
            )
        if self.line_ids.filtered(lambda line: self.currency_id.compare_amounts(line.amount, 0) < 0):
            raise UserError(_("The amount allocated to a debt can't be negative."))
        # Until it is decided whether the excess becomes an advance, a debt can't receive more than it owes.
        if exceeded := self.line_ids.filtered(
            lambda line: self.currency_id.compare_amounts(line.amount, line.amount_residual) > 0
        ):
            raise UserError(
                _(
                    "These debts would receive more than they owe: %(debts)s",
                    debts=", ".join(exceeded.move_line_id.move_id.mapped("display_name")),
                )
            )
        self.payment_id.breakdown_ids.unlink()
        self.env["account.payment.breakdown"].create(
            [
                {"payment_id": self.payment_id.id, "move_line_id": line.move_line_id.id, "amount": line.amount}
                for line in self.line_ids
                if not self.currency_id.is_zero(line.amount)
            ]
        )


class AccountPaymentBreakdownWizardLine(models.TransientModel):
    _name = "account.payment.breakdown.wizard.line"
    _description = "Debt in the breakdown of a payment"

    wizard_id = fields.Many2one("account.payment.breakdown.wizard", required=True, ondelete="cascade")
    # Not readonly: the web client doesn't send readonly fields when it saves the wizard. The view hides it.
    move_line_id = fields.Many2one("account.move.line", string="Debt", required=True)
    move_id = fields.Many2one(related="move_line_id.move_id")
    date_maturity = fields.Date(related="move_line_id.date_maturity")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    amount_residual = fields.Monetary(compute="_compute_amount_residual", string="Amount Due")
    amount = fields.Monetary(string="Amount to Allocate")

    @api.depends("move_line_id", "currency_id")
    def _compute_amount_residual(self):
        breakdown = self.env["account.payment.breakdown"]
        for line in self:
            line.amount_residual = breakdown._get_debt_residual(line.move_line_id, line.currency_id)
