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
        help="Amount left to pay with the early payment discount, if paid by the discount date.",
    )

    def _compute_early_discount_available(self):
        """Whether the invoice gets the early discount if fully paid by its discount date, and the amount left to pay
        with it. The views compare the discount date with the payment date."""
        for line in self:
            discount = (
                line.display_type == "payment_term"
                and line.discount_date
                and line.move_id._get_early_discount_if_paid(line.discount_date)
            )
            line.early_discount_available = bool(discount)
            line.early_discount_amount_to_pay = line.amount_residual_currency - discount if discount else 0.0
