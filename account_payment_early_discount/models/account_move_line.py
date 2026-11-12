##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    early_discount_available = fields.Boolean(compute="_compute_early_discount_available")
    early_discount_amount_to_pay = fields.Monetary(
        string="Amount with Discount",
        compute="_compute_early_discount_available",
        currency_field="currency_id",
        help="Amount left to pay with the early payment discount, if paid today.",
    )

    def _compute_early_discount_available(self):
        """Whether the invoice gets the early discount if fully paid today, and the amount left to pay with it."""
        payment_date = fields.Date.context_today(self)
        for line in self:
            invoice = line.move_id
            available = line.display_type == "payment_term" and invoice._is_early_discount_eligible(
                payment_date, line.amount_residual_currency
            )
            line.early_discount_available = available
            line.early_discount_amount_to_pay = (
                line.amount_residual_currency - invoice._get_early_discount_amount() if available else 0.0
            )

    def action_register_payment(self, ctx=None):
        res = super().action_register_payment(ctx=ctx)
        context = isinstance(res, dict) and res.get("context")
        if not self.company_id[:1].use_payment_pro or not context or context.get("default_partner_type") != "customer":
            return res
        # suggest the amount with discount; Payment Pro builds the default amount from the residual in company currency,
        # at the rate of the invoice, so the invoices with discount are converted at the rate of the payment date
        lines = self.browse(context.get("default_to_pay_move_line_ids") or [])
        company_currency = lines.company_currency_id[:1]
        payment_date = fields.Date.context_today(self)
        amount = 0.0
        has_discount = False
        for line in lines:
            invoice = line.move_id
            if invoice._is_early_discount_eligible(payment_date, invoice.amount_residual):
                has_discount = True
                amount += line.currency_id._convert(
                    line.amount_residual_currency - invoice._get_early_discount_amount(),
                    company_currency,
                    line.company_id,
                    payment_date,
                )
            else:
                amount += line.amount_residual
        if has_discount:
            context["default_amount"] = company_currency.round(abs(amount))
            context["default_amount_exact"] = context["default_amount"]
        context["default_early_discount_suggested_amount"] = context["default_amount"]
        return res
