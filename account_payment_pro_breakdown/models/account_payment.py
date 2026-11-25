from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    breakdown_ids = fields.One2many(
        "account.payment.breakdown",
        "payment_id",
        string="Breakdown",
        copy=False,
    )
    breakdown_difference = fields.Monetary(
        currency_field="counterpart_currency_id",
        compute="_compute_breakdown_difference",
        help="Payment amount minus the amounts allocated in the breakdown.",
    )
    breakdown_mismatch = fields.Boolean(compute="_compute_breakdown_difference")

    @api.depends("breakdown_ids.amount", "counterpart_currency_amount", "counterpart_currency_id")
    def _compute_breakdown_difference(self):
        for payment in self:
            payment.breakdown_difference = (
                payment.counterpart_currency_amount - sum(payment.breakdown_ids.mapped("amount"))
                if payment.breakdown_ids
                else 0.0
            )
            payment.breakdown_mismatch = bool(payment.counterpart_currency_id) and not (
                payment.counterpart_currency_id.is_zero(payment.breakdown_difference)
            )

    def _get_breakdown_unavailable_reason(self):
        """Return why the amount of this payment can't be broken down, or False when it can."""
        self.ensure_one()
        if self.state != "draft":
            return _("Only draft payments can be broken down.")
        if not self.use_payment_pro or self.is_internal_transfer:
            return _("Only payments to a partner that use Payment Pro can be broken down.")
        if not self.to_pay_move_line_ids:
            return _("Select the debts to pay first.")
        # Until it is decided what the total to break down is when the counterpart covers more than the cash.
        if self.write_off_amount or self._prepare_move_withholding_lines({}):
            return _("Payments with write-off or withholdings can't be broken down yet.")
        return False

    def _get_breakdown_label(self):
        """Name the payment in a message: a draft payment has no number yet."""
        self.ensure_one()
        if self.name and self.name != "/":
            return self.name
        return f"{self.partner_id.display_name} ({self.currency_id.format(self.amount)})"

    def _check_breakdown(self):
        """Block the posting of a payment whose breakdown no longer matches the payment."""
        breakdown = self.env["account.payment.breakdown"]
        for payment in self.filtered("breakdown_ids"):
            currency = payment.counterpart_currency_id
            label = payment._get_breakdown_label()
            if payment.breakdown_mismatch:
                raise UserError(
                    _(
                        "The breakdown of %(payment)s does not add up to the payment amount. Difference: %(difference)s",
                        payment=label,
                        difference=currency.format(payment.breakdown_difference),
                    )
                )
            if not_selected := payment.breakdown_ids.move_line_id - payment.to_pay_move_line_ids:
                raise UserError(
                    _(
                        "The breakdown of %(payment)s has debts that are no longer selected: %(debts)s. "
                        "Break down the amount again.",
                        payment=label,
                        debts=", ".join(not_selected.move_id.mapped("display_name")),
                    )
                )
            if exceeded := payment.breakdown_ids.filtered(
                lambda line: currency.compare_amounts(
                    line.amount, breakdown._get_debt_residual(line.move_line_id, currency)
                )
                > 0
            ):
                raise UserError(
                    _(
                        "In the breakdown of %(payment)s these debts receive more than they owe: %(debts)s",
                        payment=label,
                        debts=", ".join(exceeded.move_id.mapped("display_name")),
                    )
                )
            if payment.write_off_amount or payment._prepare_move_withholding_lines({}):
                raise UserError(
                    _(
                        "%(payment)s has a breakdown and write-off or withholdings, which can't be combined yet. "
                        "Remove the breakdown or the write-off and withholdings.",
                        payment=label,
                    )
                )

    def action_post(self):
        to_post = self.filtered(lambda payment: payment.state == "draft")
        to_post._check_breakdown()
        # A payment back to draft keeps its entry: its breakdown may have changed since it was split.
        to_post.filtered(lambda payment: payment.move_id.state == "draft")._apply_breakdown_to_move()
        return super().action_post()

    # --- Journal entry ---

    def _generate_journal_entry(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        res = super()._generate_journal_entry(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance, line_ids=line_ids
        )
        # The core posts the entry right after creating it: split it before.
        self.filtered("breakdown_ids")._apply_breakdown_to_move()
        return res

    def _synchronize_to_moves(self, changed_fields):
        if not any(field_name in changed_fields for field_name in self._get_trigger_fields_to_synchronize()):
            return super()._synchronize_to_moves(changed_fields)
        # The core rewrites a single counterpart line: merge the parts before and split them again after.
        split = self.filtered(
            lambda payment: payment.move_id.state == "draft" and len(payment._seek_for_lines()[1]) > 1
        )
        split._merge_breakdown_counterparts()
        res = super()._synchronize_to_moves(changed_fields)
        split._apply_breakdown_to_move(raise_on_mismatch=False)
        return res

    def _merge_breakdown_counterparts(self):
        """Leave the counterpart of each draft entry as a single line, as the core builds it."""
        for payment in self.filtered(lambda payment: payment.move_id.state == "draft"):
            counterparts = payment._seek_for_lines()[1]
            if len(counterparts) < 2 and not counterparts.breakdown_debt_line_id:
                continue
            move = payment.move_id
            container = {"records": move}
            with move._check_balanced(container), move._sync_dynamic_lines(container):
                counterparts[0].write(
                    {
                        "balance": sum(counterparts.mapped("balance")),
                        "amount_currency": sum(counterparts.mapped("amount_currency")),
                        "breakdown_debt_line_id": False,
                    }
                )
                counterparts[1:].unlink()

    def _apply_breakdown_to_move(self, raise_on_mismatch=True):
        """Leave the counterpart of each draft entry as one line per debt of the breakdown.

        Idempotent: the parts are merged first, so the entry always follows the current breakdown.
        """
        self._merge_breakdown_counterparts()
        for payment in self.filtered(lambda payment: payment.move_id.state == "draft" and payment.breakdown_ids):
            counterpart = payment._seek_for_lines()[1]
            if len(counterpart) != 1:
                continue
            currency = counterpart.currency_id
            total = abs(counterpart.amount_currency)
            if payment.breakdown_mismatch or currency.compare_amounts(
                sum(payment.breakdown_ids.mapped("amount")), total
            ):
                if raise_on_mismatch:
                    raise UserError(
                        _(
                            "The breakdown of %(payment)s does not match its journal entry. Break down the amount again.",
                            payment=payment._get_breakdown_label(),
                        )
                    )
                continue
            sign = -1 if counterpart.amount_currency < 0 else 1
            company_currency = counterpart.company_currency_id
            balance_left = counterpart.balance
            parts = []
            for index, breakdown in enumerate(payment.breakdown_ids):
                amount_currency = sign * breakdown.amount
                if index == len(payment.breakdown_ids) - 1:
                    # The last part takes the rounding, so the parts add up to the original balance.
                    balance = balance_left
                elif currency == company_currency:
                    balance = amount_currency
                else:
                    balance = company_currency.round(counterpart.balance * breakdown.amount / total)
                balance_left -= balance
                parts.append(
                    {
                        "amount_currency": amount_currency,
                        "balance": balance,
                        "breakdown_debt_line_id": breakdown.move_line_id.id,
                    }
                )
            move = payment.move_id
            container = {"records": move}
            with move._check_balanced(container), move._sync_dynamic_lines(container):
                # balance and amount_currency go together: create recomputes balance from a copied amount_currency.
                new_parts = [counterpart.copy_data(vals)[0] for vals in parts[1:]]
                counterpart.write(parts[0])
                self.env["account.move.line"].create(new_parts)

    def _reconcile_after_post(self):
        # Each part with its own debt first: the core reconciliation then finds no counterpart left to spread.
        for payment in self.filtered(
            lambda payment: payment.breakdown_ids
            and payment.company_id.use_payment_pro
            and not payment.is_internal_transfer
        ):
            for part in payment.move_id.line_ids.filtered(
                lambda line: line.breakdown_debt_line_id and not line.reconciled and line.move_id.state == "posted"
            ):
                to_reconcile = part + part.breakdown_debt_line_id
                # The debt may be of a branch the user has no access to, as in account_payment_pro.
                if to_reconcile.company_id - self.env.companies:
                    to_reconcile = to_reconcile.sudo()
                to_reconcile.reconcile()
        return super()._reconcile_after_post()

    def action_open_breakdown_wizard(self):
        self.ensure_one()
        if reason := self._get_breakdown_unavailable_reason():
            raise UserError(reason)
        return {
            "name": _("Payment Breakdown"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment.breakdown.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }
