##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    early_discount_apply = fields.Boolean(
        string="Apply Early Payment Discount",
        default=True,
        copy=False,
        help="Uncheck it so this payment does not apply the early payment discount, although the invoices get it.",
    )
    early_discount_available = fields.Boolean(compute="_compute_early_discount_amount")
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
    early_discount_suggested_amount = fields.Monetary(
        currency_field="currency_id",
        help="Last amount suggested on the payment, to update it when the payment date changes.",
    )
    early_discount_warning_credit_note_ids = fields.Many2many(
        "account.move",
        string="Early Discount Credit Notes",
        compute="_compute_early_discount_warning_credit_note_ids",
        help="Posted early payment discount credit notes created by this payment, when the payment was cancelled or "
        "one of its checks was returned to the customer.",
    )

    @api.depends(
        "to_pay_move_line_ids",
        "payment_total",
        "payment_difference",
        "write_off_amount",
        "date",
        "state",
        "early_discount_apply",
    )
    def _compute_early_discount_amount(self):
        for rec in self:
            available = sum(rec._early_discount_allocation().values()) if rec._is_early_discount_payment() else 0.0
            amount = available if rec.early_discount_apply else 0.0
            rec.early_discount_available = bool(available)
            rec.early_discount_amount = amount
            rec.early_discount_difference = rec.payment_difference - amount

    @api.depends("state")
    def _compute_early_discount_warning_credit_note_ids(self):
        to_warn = self.filtered(lambda x: x.id and (x.state == "canceled" or x._is_early_discount_check_returned()))
        credit_notes = self.env["account.move"].search(
            [("early_discount_payment_id", "in", to_warn.ids), ("state", "=", "posted")]
        )
        for rec in self:
            rec.early_discount_warning_credit_note_ids = credit_notes.filtered(
                lambda move: move.early_discount_payment_id == rec
            )

    def _is_early_discount_check_returned(self):
        """Whether a check received in this payment was returned to the customer, like when it is rejected."""
        self.ensure_one()
        if "l10n_latam_new_check_ids" not in self._fields:
            return False
        return any(
            operation.state not in ("draft", "canceled")
            and operation.payment_type == "outbound"
            and operation.partner_type == "customer"
            and operation.payment_method_code in ("return_third_party_checks", "out_third_party_checks")
            for check in self.l10n_latam_new_check_ids
            for operation in check.operation_ids
        )

    @api.onchange("to_pay_move_line_ids")
    def _onchange_to_pay_lines_adjust_amount(self):
        previous_amounts = [rec.amount for rec in self]
        super()._onchange_to_pay_lines_adjust_amount()
        # on new payments, suggest the amount with discount instead of the full debt
        for rec, previous_amount in zip(self, previous_amounts):
            if rec._origin.id or not rec._is_early_discount_payment():
                continue
            if rec.destination_currency_id.is_zero(rec.payment_difference):
                discount = rec._get_early_discount_to_apply()
                if discount:
                    rec.amount = rec.amount - rec._early_discount_to_payment_currency(discount)
                    rec.amount_exact = rec.amount
            if rec.currency_id.compare_amounts(rec.amount, previous_amount):
                rec.early_discount_suggested_amount = rec.amount

    @api.onchange("date", "early_discount_apply")
    def _onchange_early_discount_suggested_amount(self):
        # when the date moves in or out of the discount period, or the discount is turned on or off, update the amount
        # if it is still a suggestion
        for rec in self:
            if rec._origin.id or not rec._is_early_discount_payment() or rec.write_off_amount:
                continue
            currency = rec.destination_currency_id
            invoices = rec._get_early_discount_debt_lines().move_id.filtered(
                lambda move: move.invoice_payment_term_id.early_discount and move.currency_id == currency
            )
            term_discount = sum(invoice._get_early_discount_amount() for invoice in invoices)
            # with a debt in another currency the difference changes with the rate, so the last suggestion is checked too
            is_suggestion = (
                rec.early_discount_suggested_amount
                and rec.currency_id.compare_amounts(rec.amount, rec.early_discount_suggested_amount) == 0
            )
            if not is_suggestion and not any(
                currency.is_zero(rec.payment_difference - suggested) for suggested in (0.0, term_discount)
            ):
                continue
            rec.amount = rec._get_early_discount_suggested_amount(0.0)
            rec.amount_exact = rec.amount
            discount = rec._get_early_discount_to_apply()
            rec.amount = rec._get_early_discount_suggested_amount(discount)
            rec.amount_exact = rec.amount
            rec.early_discount_suggested_amount = rec.amount

    def action_adjust_amount_for_difference(self):
        # with the early discount applied, adjust the difference after the discount, so the discount is kept
        discounted = self.filtered("early_discount_amount")
        for rec in discounted:
            if rec.destination_currency_id.is_zero(rec.early_discount_difference):
                continue
            amount = rec.amount_exact + rec._early_discount_to_payment_currency(rec.early_discount_difference)
            if amount >= 0:
                rec.amount_exact = amount
                rec.amount = amount
        return super(AccountPayment, self - discounted).action_adjust_amount_for_difference()

    def action_adjust_writeoff_for_difference(self):
        # with the early discount applied, send to write-off only the difference after the discount
        discounted = self.filtered("early_discount_amount")
        for rec in discounted:
            if not rec.destination_currency_id.is_zero(rec.early_discount_difference):
                rec.write_off_amount += rec.early_discount_difference
        return super(AccountPayment, self - discounted).action_adjust_writeoff_for_difference()

    def action_post(self):
        for rec in self.filtered(lambda x: x._is_early_discount_payment() and x.early_discount_apply):
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

    def _get_early_discount_to_apply(self):
        """Early discount the payment applies, unless it is turned off on the payment."""
        self.ensure_one()
        return sum(self._early_discount_allocation().values()) if self.early_discount_apply else 0.0

    def _early_discount_to_payment_currency(self, amount):
        """Convert an amount in the currency of the payment total to the payment currency, as Payment Pro does
        with the payment difference."""
        self.ensure_one()
        if self.counterpart_currency_id != self.destination_currency_id:
            return amount * (self.accounting_rate or 1.0)
        return amount / (self.counterpart_rate or 1.0)

    def _get_early_discount_suggested_amount(self, discount):
        """Payment amount that leaves only ``discount`` as payment difference. It is computed from the debt and not
        from the payment difference, which is rounded in the currency of the payment total."""
        self.ensure_one()
        amount = self.amount_exact or self.amount
        if self.counterpart_currency_id != self.destination_currency_id:
            amount_in_total_currency = amount / (self.accounting_rate or 1.0)
        else:
            amount_in_total_currency = amount * (self.counterpart_rate or 1.0)
        # write-off and other amounts of the payment total, like withholdings
        others = self.destination_currency_id.round(self.payment_total - amount_in_total_currency)
        return self._early_discount_to_payment_currency(self.to_pay_amount - others - discount)

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
                    invoice._apply_early_discount().early_discount_payment_id = self
                    # a credit note left in draft by a customization does not reduce the residual
                    discount = residual - self._get_early_discount_residual(line)
                else:
                    discount = invoice._get_early_discount_amount()
                if discount:
                    discounts[invoice] = discount
                residual -= discount
            available -= residual
        return discounts
