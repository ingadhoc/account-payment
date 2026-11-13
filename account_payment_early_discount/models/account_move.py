##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from collections import defaultdict

from odoo import Command, _, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    is_early_discount = fields.Boolean(
        copy=False,
        readonly=True,
        help="Credit note created by the early payment discount.",
    )
    early_discount_payment_id = fields.Many2one(
        "account.payment",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Payment that created this early payment discount credit note.",
    )

    def _is_early_discount_eligible(self, payment_date, amount):
        """Return whether paying ``amount`` (in invoice currency) on ``payment_date`` gets the early discount."""
        self.ensure_one()
        term = self.invoice_payment_term_id
        term_line = self.line_ids.filtered(lambda line: line.display_type == "payment_term")
        if (
            not self.company_id.use_payment_pro
            or self.move_type != "out_invoice"
            or self.state != "posted"
            # reconciling on company currency, payments work in company currency and do not apply the discount
            or (self.company_id.reconcile_on_company_currency and self.currency_id != self.company_currency_id)
            or not term.early_discount
            or term.early_pay_discount_computation != "included"
            or len(term_line) != 1
            or not term_line.discount_date
            or payment_date > term_line.discount_date
            or self.reversal_move_ids.filtered(lambda move: move.is_early_discount and move.state != "cancel")
        ):
            return False
        # every previous payment must also be within the discount period; credit notes do not count as payments
        if any(
            partial.credit_move_id.date > term_line.discount_date
            and partial.credit_move_id.move_id.move_type != "out_refund"
            for partial in term_line.matched_credit_ids
        ):
            return False
        required = term_line.amount_residual_currency - self._get_early_discount_amount()
        return self.currency_id.compare_amounts(amount, required) >= 0

    def _get_early_discount_amount(self):
        """Early discount of the invoice according to its payment term, in invoice currency. Regular credit notes
        linked to the invoice reduce it in proportion, so the discount is computed on what is owed."""
        self.ensure_one()
        term_line = self.line_ids.filtered(lambda line: line.display_type == "payment_term")
        discount = sum(term_line.mapped("amount_currency")) - sum(term_line.mapped("discount_amount_currency"))
        credit_notes = self._get_early_discount_regular_credit_notes()
        if credit_notes and self.amount_total:
            discount *= max(1 - sum(credit_notes.mapped("amount_total")) / self.amount_total, 0.0)
        return self.currency_id.round(discount)

    def _get_early_discount_regular_credit_notes(self):
        """Posted credit notes linked to the invoice that are not early discount ones."""
        self.ensure_one()
        return self.reversal_move_ids.filtered(lambda move: move.state == "posted" and not move.is_early_discount)

    def _prepare_early_discount_reversal_vals(self):
        """Values for the credit note wizard; the credit note is dated when the payment is posted."""
        self.ensure_one()
        return {
            "move_ids": [Command.set(self.ids)],
            "journal_id": self.journal_id.id,
            "date": fields.Date.context_today(self),
            "reason": _("Early payment discount"),
        }

    def _prepare_early_discount_line_vals(self):
        """One credit note line per set of taxes of the invoice lines, for the discount percentage of their base.
        The base of the regular credit notes linked to the invoice is subtracted."""
        self.ensure_one()
        percentage = self.invoice_payment_term_id.discount_percentage / 100
        account = self.company_id.account_journal_early_pay_discount_loss_account_id
        bases = defaultdict(float)
        moves = [(self, 1)] + [(move, -1) for move in self._get_early_discount_regular_credit_notes()]
        for move, sign in moves:
            for line in move.invoice_line_ids.filtered(lambda line: line.display_type == "product"):
                taxes = line.tax_ids.filtered(lambda tax: tax.amount_type != "fixed")
                # same price basis as the invoice line, so price-included taxes are respected
                bases[taxes] += sign * line.price_unit * line.quantity * (1 - line.discount / 100)
        return [
            {
                "name": _("Early payment discount"),
                "account_id": account.id,
                "quantity": 1,
                "price_unit": self.currency_id.round(base * percentage),
                "tax_ids": [Command.set(taxes.ids)],
            }
            for taxes, base in bases.items()
            if self.currency_id.compare_amounts(base * percentage, 0) > 0
        ]

    def _create_early_discount_credit_note(self):
        """Create the early discount credit note in draft through the credit note wizard."""
        self.ensure_one()
        wizard = (
            self.env["account.move.reversal"]
            .with_context(active_model="account.move", active_ids=self.ids)
            .create(self._prepare_early_discount_reversal_vals())
        )
        wizard.refund_moves()
        credit_note = wizard.new_move_ids
        # the wizard copies every line of the invoice
        credit_note.line_ids.filtered(lambda line: line.display_type not in ("payment_term", "tax")).unlink()
        lines_vals = self._fix_early_discount_tax_amounts(credit_note, self._prepare_early_discount_line_vals())
        credit_note.write(
            {
                "is_early_discount": True,
                "invoice_line_ids": [Command.create(vals) for vals in lines_vals],
            }
        )
        return credit_note

    def _fix_early_discount_tax_amounts(self, credit_note, lines_vals):
        """Fix the amounts of the taxes charged on the invoice as computed line by line, so the credit note refunds
        them even when a threshold of the whole document (e.g. the minimum base of a perception) is not reached."""
        self.ensure_one()
        AccountTax = self.env["account.tax"]
        invoice_taxes = self.line_ids.tax_line_id
        lines = [self.env["account.move.line"].new({**vals, "move_id": credit_note.id}) for vals in lines_vals]
        base_lines = [credit_note._prepare_product_base_line_for_taxes_computation(line) for line in lines]
        for base_line in base_lines:
            AccountTax._add_tax_details_in_base_line(base_line, credit_note.company_id)
        AccountTax._round_base_lines_tax_details(base_lines, credit_note.company_id)
        AccountTax._fix_base_lines_tax_details_on_manual_tax_amounts(
            base_lines,
            credit_note.company_id,
            filter_function=lambda base_line, tax_data: tax_data["tax"] in invoice_taxes,
        )
        return [
            {**vals, "extra_tax_data": AccountTax._export_base_line_extra_tax_data(base_line)}
            for vals, base_line in zip(lines_vals, base_lines)
        ]

    def _post_early_discount_credit_note(self):
        """Post the early discount credit notes; override to leave them in draft."""
        self.action_post()

    def _apply_early_discount(self):
        """Create the early discount credit note and, once posted, reconcile it with this invoice."""
        self.ensure_one()
        credit_note = self._create_early_discount_credit_note()
        credit_note._post_early_discount_credit_note()
        if credit_note.state == "posted":
            (credit_note + self).line_ids.filtered(
                lambda line: line.display_type == "payment_term" and not line.reconciled
            ).reconcile()
        return credit_note
