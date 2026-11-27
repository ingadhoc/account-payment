from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    amount_locked = fields.Boolean(
        default=True,
        copy=False,
        help="When locked, changing the debt of a new payment keeps the amount loaded by the user. "
        "Unlock it to let the amount follow the selected debt.",
    )

    @api.onchange("to_pay_move_line_ids")
    def _onchange_to_pay_lines_adjust_amount(self):
        """With the amount locked, only follow the debt with an amount proposed by the
        system: zero, or the one sent by register payment. Unlocked payments keep the
        standard behavior."""
        proposed = self.env.context.get("default_amount")
        to_adjust = self.filtered(
            lambda rec: not rec.amount_locked
            or not rec.currency_id
            or rec.currency_id.is_zero(rec.amount)
            or (proposed and rec.currency_id.is_zero(rec.amount - proposed))
        )
        return super(AccountPayment, to_adjust)._onchange_to_pay_lines_adjust_amount()
