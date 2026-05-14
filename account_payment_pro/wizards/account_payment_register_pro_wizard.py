##############################################################################
# For copyright and license notices, see __manifest__.py file in root directory
##############################################################################
from odoo import Command, _, api, fields, models

_CHECK_CODES = frozenset(
    [
        "own_checks",
        "new_third_party_checks",
        "in_third_party_checks",
        "out_third_party_checks",
        "return_third_party_checks",
        "payment_bundle",
    ]
)


class AccountPaymentRegisterProWizard(models.TransientModel):
    """Thin extension of account.payment.register that adds:
    - fiscal_position_mode: Automatic / Manual selector (supplier-only)
    - action_create_and_confirm: create + post all payments
    - action_create_draft: create in draft and navigate to list view
    """

    _inherit = "account.payment.register"

    fiscal_position_mode = fields.Selection(
        [("automatic", "Automatic"), ("manual", "Manual")],
        default="automatic",
        required=True,
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        string="Fiscal Position (Payment Pro)",
        check_company=True,
    )
    is_payment_pro = fields.Boolean(
        default=lambda self: bool(self.env.context.get("payment_pro")),
    )

    @api.depends("is_payment_pro")
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for wizard in self:
            if not wizard.is_payment_pro:
                continue
            # Exclude journals that have NO method outside check/bundle (purely check/bundle journals).
            # Mixed journals (e.g. Bank with Manual + own_checks) are kept;
            # the method filter below removes individual check/bundle lines.
            wizard.available_journal_ids = wizard.available_journal_ids.filtered(
                lambda j: (
                    set(
                        j.inbound_payment_method_line_ids.payment_method_id.mapped("code")
                        + j.outbound_payment_method_line_ids.payment_method_id.mapped("code")
                    )
                    - _CHECK_CODES
                )
            )

    @api.depends("is_payment_pro")
    def _compute_payment_method_line_fields(self):
        super()._compute_payment_method_line_fields()
        for wizard in self:
            if not wizard.is_payment_pro:
                continue
            wizard.available_payment_method_line_ids = wizard.available_payment_method_line_ids.filtered(
                lambda l: l.payment_method_id.code not in _CHECK_CODES
            )

    def _get_debt_line_ids_cmd(self, batch_result):
        valid_types = {"asset_receivable", "liability_payable"}
        debt_lines = batch_result["lines"].filtered(lambda l: l.account_id.account_type in valid_types)
        return [Command.set(debt_lines.ids)] if debt_lines else []

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if not self.is_payment_pro:
            return payment_vals
        # Strip withholding write_off entries — the payment's l10n_ar_withholding_line_ids
        # creates the journal lines via _prepare_move_withholding_lines at action_post time.
        payment_vals["write_off_line_vals"] = [
            v
            for v in payment_vals.get("write_off_line_vals", [])
            if not v.get("tax_repartition_line_id") and not v.get("tax_ids")
        ]
        # Embed to_pay_move_line_ids so l10n_ar_fiscal_position_id resolves at payment
        # creation time, triggering withholding computation before action_post.
        debt_cmd = self._get_debt_line_ids_cmd(batch_result)
        if debt_cmd:
            payment_vals.setdefault("to_pay_move_line_ids", debt_cmd)
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        if not self.is_payment_pro:
            return payment_vals
        # Same as wizard path: embed to_pay_move_line_ids for multi-partner batches.
        debt_cmd = self._get_debt_line_ids_cmd(batch_result)
        if debt_cmd:
            payment_vals.setdefault("to_pay_move_line_ids", debt_cmd)
        return payment_vals

    def _init_payments(self, to_process, edit_mode=False):
        if self.env.context.get("payment_pro_draft"):
            for vals in to_process:
                for key in ("write_off_line_vals", "force_balance", "line_ids"):
                    vals["create_vals"].pop(key, None)
        payments = super()._init_payments(to_process, edit_mode=edit_mode)
        if not self.is_payment_pro:
            return payments
        # Flush pending stored computed fields (l10n_ar_withholding_line_ids,
        # withholdings_amount) triggered by to_pay_move_line_ids set at creation.
        self.env.flush_all()
        # amount must equal (to_pay_amount - withholdings_amount) so that:
        #   payment_total = amount + withholdings_amount == to_pay_amount
        # For single-partner, l10n_ar_withholding already reduces the wizard amount;
        # for multi-partner batches the wizard carries no withholdings, so we correct here.
        for vals in to_process:
            payment = vals["payment"]
            withholdings = getattr(payment, "withholdings_amount", 0.0)
            if not withholdings:
                continue
            net = payment.to_pay_amount - withholdings
            if net > 0 and not payment.currency_id.is_zero(net - payment.amount):
                payment.write({"amount": net, "amount_exact": net})
        return payments

    def _post_payments(self, to_process, edit_mode=False):
        if not self.env.context.get("payment_pro_draft"):
            return super()._post_payments(to_process, edit_mode=edit_mode)

    def _reconcile_payments(self, to_process, edit_mode=False):
        valid_types = {"asset_receivable", "liability_payable"}
        for vals in to_process:
            payment = vals["payment"]
            if payment.company_id.use_payment_pro:
                debt_lines = vals["to_reconcile"].filtered(lambda l: l.account_id.account_type in valid_types)
                if debt_lines and not payment.to_pay_move_line_ids:
                    payment.to_pay_move_line_ids = [Command.set(debt_lines.ids)]
        if not self.env.context.get("payment_pro_draft"):
            return super()._reconcile_payments(to_process, edit_mode=edit_mode)

    def _create_payments(self):
        payments = super(
            AccountPaymentRegisterProWizard, self.with_context(skip_to_pay_compute=True)
        )._create_payments()
        if self.fiscal_position_mode == "manual" and self.fiscal_position_id:
            if hasattr(payments, "fiscal_position_id"):
                payments.fiscal_position_id = self.fiscal_position_id
            if hasattr(payments, "l10n_ar_fiscal_position_id"):
                payments.l10n_ar_fiscal_position_id = self.fiscal_position_id
        return payments

    def action_create_and_confirm(self):
        return self.action_create_payments()

    def action_create_draft(self):
        payments = self.with_context(payment_pro_draft=True)._create_payments()
        return {
            "name": _("Payments"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", payments.ids)],
            "context": {"create": False},
            "target": "current",
        }
