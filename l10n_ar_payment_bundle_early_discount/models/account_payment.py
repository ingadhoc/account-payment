##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    bundle_early_discount_applied = fields.Monetary(
        string="Early Payment Discount Applied",
        compute="_compute_early_discount_amount",
        currency_field="destination_currency_id",
        help="Early payment discount of the invoices that the linked payments already pay, the one applied if the "
        "payment is posted now.",
    )

    def _is_early_discount_receipt(self):
        # on a bundle the main payment decides and applies the discount, with its own date
        return super()._is_early_discount_receipt() and not self.main_payment_id

    def _is_early_discount_check_returned(self):
        # the credit notes belong to the main payment, but the checks are received in the linked payments
        return super()._is_early_discount_check_returned() or any(
            link._is_early_discount_check_returned() for link in self.link_payment_ids
        )

    @api.onchange("to_pay_move_line_ids", "is_main_payment")
    def _onchange_to_pay_lines_adjust_amount(self):
        super()._onchange_to_pay_lines_adjust_amount()
        # the main payment amount is always zero, the discount is suggested on the linked payments
        main_payments = self.filtered("is_main_payment")
        main_payments.amount = 0.0
        main_payments.amount_exact = 0.0
        main_payments.early_discount_suggested_amount = 0.0

    def _early_discount_update_suggested_amount(self):
        return super(AccountPayment, self - self.filtered("is_main_payment"))._early_discount_update_suggested_amount()

    def _compute_early_discount_amount(self):
        # while the bundle is built, the difference of the main payment has the discount it gets if it pays all the
        # selected debt, and the discount shown is the one of the invoices already paid, as the credit notes
        main_payments = self.filtered(lambda x: x.is_main_payment and x._is_early_discount_payment())
        super(AccountPayment, self - main_payments)._compute_early_discount_amount()
        (self - main_payments).bundle_early_discount_applied = 0.0
        for rec in main_payments:
            available = rec._get_bundle_early_discount_available()
            amount = available if rec.early_discount_apply else 0.0
            rec.early_discount_available = bool(available)
            rec.early_discount_amount = amount
            rec.early_discount_difference = rec.payment_difference - amount
            rec.bundle_early_discount_applied = (
                sum(rec._early_discount_allocation().values()) if rec.early_discount_apply else 0.0
            )

    @api.depends("main_payment_id.early_discount_amount")
    def _compute_payment_difference(self):
        super()._compute_payment_difference()
        for rec in self.filtered("main_payment_id"):
            rec.payment_difference -= rec.main_payment_id.early_discount_amount

    def _get_bundle_early_discount_available(self):
        """Early discount of the selected debt if the bundle pays all of it, as the amount with discount is
        suggested on a regular payment."""
        self.ensure_one()
        currency = self.destination_currency_id or self.company_currency_id
        return sum(
            line.move_id._get_early_discount_amount()
            for line in self._get_early_discount_debt_lines()
            if line.currency_id == currency
            and line.move_id._is_early_discount_eligible(self.date, self._get_early_discount_residual(line))
        )
