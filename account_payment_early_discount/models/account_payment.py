##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    early_discount_amount = fields.Monetary(
        string="Early Payment Discount",
        compute="_compute_early_discount_amount",
        currency_field="destination_currency_id",
        help="Early payment discount that will be applied as credit notes when the payment is posted.",
    )
    early_discount_difference = fields.Monetary(
        string="Difference after discount",
        compute="_compute_early_discount_amount",
        currency_field="destination_currency_id",
    )
    early_discount_write_off_warning = fields.Boolean(compute="_compute_early_discount_amount")

    @api.depends("to_pay_move_line_ids", "payment_total", "payment_difference", "write_off_amount", "date", "state")
    def _compute_early_discount_amount(self):
        for rec in self:
            amount = sum(rec._early_discount_allocation().values()) if rec._is_early_discount_payment() else 0.0
            rec.early_discount_amount = amount
            rec.early_discount_difference = rec.payment_difference - amount
            currency = rec.destination_currency_id or rec.company_currency_id
            rec.early_discount_write_off_warning = bool(
                amount and rec.write_off_amount and currency.compare_amounts(rec.early_discount_difference, 0) < 0
            )

    @api.onchange("to_pay_move_line_ids")
    def _onchange_to_pay_lines_adjust_amount(self):
        super()._onchange_to_pay_lines_adjust_amount()
        # on new payments, suggest the amount with discount instead of the full debt
        for rec in self:
            if (
                rec._origin.id
                or not rec._is_early_discount_payment()
                or not rec.destination_currency_id.is_zero(rec.payment_difference)
            ):
                continue
            discount = sum(rec._early_discount_allocation().values())
            if discount:
                rec.amount = rec.amount - rec._early_discount_to_payment_currency(discount)
                rec.amount_exact = rec.amount

    @api.onchange("date")
    def _onchange_date_early_discount_amount(self):
        # when the date moves in or out of the discount period, update the amount if it is still a suggestion
        for rec in self:
            if rec._origin.id or not rec._is_early_discount_payment() or rec.write_off_amount:
                continue
            currency = rec.destination_currency_id
            invoices = rec._get_early_discount_debt_lines().move_id.filtered(
                lambda move: move.invoice_payment_term_id.early_discount and move.currency_id == currency
            )
            term_discount = sum(invoice._get_early_discount_amount() for invoice in invoices)
            if not any(currency.is_zero(rec.payment_difference - suggested) for suggested in (0.0, term_discount)):
                continue
            rec.amount = rec.amount + rec._early_discount_to_payment_currency(rec.payment_difference)
            discount = sum(rec._early_discount_allocation().values())
            rec.amount = rec.amount - rec._early_discount_to_payment_currency(discount)
            rec.amount_exact = rec.amount

    def action_post(self):
        for rec in self.filtered(lambda x: x._is_early_discount_payment()):
            rec._early_discount_allocation(apply=True)
        return super().action_post()

    def _is_early_discount_payment(self):
        self.ensure_one()
        return (
            self.state == "draft"
            and self.company_id.use_payment_pro
            and self.partner_type == "customer"
            and self.payment_type == "inbound"
            and not self.is_internal_transfer
        )

    def _early_discount_to_payment_currency(self, amount):
        """Convert an amount in the currency of the payment total to the payment currency, as Payment Pro does
        with the payment difference."""
        self.ensure_one()
        if self.counterpart_currency_id != self.destination_currency_id:
            return amount * (self.accounting_rate or 1.0)
        return amount / (self.counterpart_rate or 1.0)

    def _get_early_discount_residual(self, line):
        """Residual of a debt line in the currency of the payment total, as Payment Pro computes the selected debt."""
        self.ensure_one()
        if self.destination_currency_id and self.destination_currency_id != self.company_currency_id:
            return line.amount_residual_currency
        return line.amount_residual

    def _get_early_discount_debt_lines(self):
        """Selected debt lines in the order the reconciliation pays them: oldest due date first."""
        self.ensure_one()
        return self.to_pay_move_line_ids.filtered(lambda line: line.amount_residual > 0).sorted(
            lambda line: (
                line.date_maturity or line.date,
                line.currency_id.id,
                line.amount_currency,
                line.balance,
            )
        )

    def _early_discount_allocation(self, apply=False):
        """Spread the payment over the selected debt by due date and return the early discount of every invoice
        that gets fully paid within the discount period. With ``apply`` the credit notes are created."""
        self.ensure_one()
        currency = self.destination_currency_id or self.company_currency_id
        credits = self.to_pay_move_line_ids.filtered(lambda line: line.amount_residual < 0)
        available = self.payment_total - sum(self._get_early_discount_residual(line) for line in credits)
        discounts = {}
        for line in self._get_early_discount_debt_lines():
            if currency.compare_amounts(available, 0) <= 0:
                break
            invoice = line.move_id
            residual = self._get_early_discount_residual(line)
            if line.currency_id == currency and invoice._is_early_discount_eligible(self.date, available):
                if apply:
                    invoice._apply_early_discount()
                    # a credit note left in draft by a customization does not reduce the residual
                    discount = residual - self._get_early_discount_residual(line)
                else:
                    discount = invoice._get_early_discount_amount()
                if discount:
                    discounts[invoice] = discount
                residual -= discount
            available -= residual
        return discounts
