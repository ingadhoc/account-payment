##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    early_discount_available = fields.Boolean(compute="_compute_early_discount_available")

    def _compute_early_discount_available(self):
        """Whether the invoice gets the early discount if fully paid today."""
        payment_date = fields.Date.context_today(self)
        for line in self:
            line.early_discount_available = (
                line.display_type == "payment_term"
                and line.move_id._is_early_discount_eligible(payment_date, line.amount_residual_currency)
            )

    def action_register_payment(self, ctx=None):
        res = super().action_register_payment(ctx=ctx)
        context = isinstance(res, dict) and res.get("context")
        if not context or context.get("default_partner_type") != "customer" or "default_amount" not in context:
            return res
        # suggest the amount with discount; Payment Pro builds the default amount from the residual in company currency
        lines = self.browse(context.get("default_to_pay_move_line_ids") or [])
        payment_date = fields.Date.context_today(self)
        discount = 0.0
        for line in lines:
            invoice = line.move_id
            if line.amount_residual_currency and invoice._is_early_discount_eligible(
                payment_date, invoice.amount_residual
            ):
                discount += invoice._get_early_discount_amount() * line.amount_residual / line.amount_residual_currency
        if discount:
            context["default_amount"] = lines.company_currency_id[:1].round(context["default_amount"] - discount)
            context["default_amount_exact"] = context["default_amount"]
        return res
