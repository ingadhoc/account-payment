from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


class PaymentTransactionRetry(models.TransientModel):
    _name = "payment.transaction.retry"
    _description = "payment transaction retry"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True, readonly=True, default=lambda self: self.env.company
    )
    asynchronous_process = fields.Boolean()
    line_ids = fields.One2many("payment.transaction.retry.lines", "retry_id")
    percentage = fields.Float(default=100)
    validate_emails = fields.Boolean(compute="_compute_validate_emails")
    message = fields.Text()
    warnings = fields.Json(
        compute="_compute_warnings",
    )

    @api.onchange("line_ids")
    def _compute_validate_emails(self):
        for rec in self:
            email_oks = True
            for partner in rec.line_ids.mapped("partner_id"):
                if not partner.email or not email_normalize(partner.email):
                    email_oks = False
            rec.validate_emails = email_oks

    @api.depends("validate_emails", "message")
    def _compute_warnings(self):
        for rec in self:
            warnings = {}
            if not rec.validate_emails:
                partners_without_mail = rec.line_ids.mapped("partner_id").filtered(
                    lambda x: not x.email or not email_normalize(x.email)
                )
                warnings["validate_emails"] = {
                    "level": "error",
                    "message": _("Partner(s) should have an email address."),
                    "action_text": _("View Partner(s)"),
                    "action": partners_without_mail._get_records_action(name=_("Check Partner(s) Email(s)")),
                }
            if rec.message:
                warnings["message"] = {
                    "level": "error",
                    "message": rec.message,
                }
            rec.warnings = warnings

    @api.onchange("percentage")
    def _onchange_percentage(self):
        for line in self.line_ids:
            line.percentage = self.percentage

    @api.model
    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        active_ids = self._context.get("active_ids") or self._context.get("active_id")
        active_model = self._context.get("active_model")
        if active_model == "account.move":
            move_ids = (
                self.env[active_model]
                .browse(active_ids)
                .filtered(
                    lambda x: x.payment_state in ["not_paid", "partial"]
                    and x.amount_residual > 0.0
                    and x.move_type in ["out_invoice", "out_refund"]
                    and x.state == "posted"
                    and not {"pending", "authorized"}.intersection(set(x.transaction_ids.mapped("state")))
                    and x.company_id == self.env.company
                )
            )
            rec["line_ids"] = [
                Command.create({"invoice_id": x.id, "amount_to_pay": x.amount_residual}) for x in move_ids
            ]
            rec["asynchronous_process"] = len(rec["line_ids"]) > 20
        return rec

    def action_create_payments(self):
        if not self.validate_emails:
            raise ValidationError(_("Partner(s) should have an email address."))

        if "bypass_check_similar_transactions" not in self.env.context:
            action_fallback = self.action_check_for_similar_transactions()
            if self.message:
                return action_fallback

        tx_ids = self.env["payment.transaction"]
        for line in self.line_ids.filtered(lambda x: x.payment_token_id and x.amount_to_pay > 0):
            txs_vals = {
                "provider_id": line.payment_token_id.provider_id.id,
                "amount": line.amount_to_pay,
                "currency_id": line.currency_id.id,
                "partner_id": line.partner_id.id,
                "token_id": line.payment_token_id.id,
                "payment_method_id": line.payment_token_id.payment_method_id.id,
                "operation": "offline",
                "invoice_ids": [Command.set([line.invoice_id.id])],
                "asynchronous_process": self.asynchronous_process,
            }
            tx_ids += self.env["payment.transaction"].sudo().create(txs_vals)
        if not self.asynchronous_process:
            for tx_id in tx_ids:
                tx_id._send_payment_request()

    @api.model
    def action_open_wizard(self):
        active_ids = self.env.context.get("active_ids")
        if not active_ids:
            return ""
        res_id = self.with_context(**self.env.context).create({})
        return {
            "name": _("Retry payments"),
            "res_model": "payment.transaction.retry",
            "view_mode": "form",
            "view_id": self.env.ref("payment_retry.payment_transaction_retry_view_form").id,
            "res_id": res_id.id,
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def action_check_for_similar_transactions(self):
        self.message = self._check_for_similar_transactions()
        return {
            "name": _("Retry payments"),
            "res_model": "payment.transaction.retry",
            "view_mode": "form",
            "view_id": self.env.ref("payment_retry.payment_transaction_retry_view_form").id,
            "res_id": self.id,
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def _check_for_similar_transactions(self):
        self.ensure_one()
        message = ""
        days_frame = int(
            self.env["ir.config_parameter"].sudo().get_param("payment_retry.similar_transactions_days_frame", 1)
        )
        partner_ids = self.line_ids.mapped("partner_id")
        token_ids = self.line_ids.mapped("payment_token_id")
        similar_tx_ids = self.env["payment.transaction"].search(
            [
                ("state", "!=", "cancel"),
                ("create_date", ">=", fields.Datetime.now() - timedelta(days=days_frame)),
                "|",
                ("token_id", "in", token_ids.ids),
                ("partner_id", "in", partner_ids.ids),
            ]
        )
        for similar_tx in similar_tx_ids:
            message += _(
                "odoo: A similar transaction of %.2f %s for %s via %s was created on %s and is currently in state %s.\n",
                similar_tx.amount,
                similar_tx.currency_id.name,
                similar_tx.partner_id.display_name,
                similar_tx.provider_id.name,
                fields.Datetime.to_string(similar_tx.create_date),
                similar_tx.state,
            )
        for provider_id, token_ids in token_ids.grouped(lambda x: x.provider_id).items():
            method = f"{provider_id.code}_check_for_similar_transactions"
            if hasattr(self.env["payment.token"], method):
                message += getattr(token_ids, method)(days_frame=days_frame)
        return message


class PaymentTransactionRetryLines(models.TransientModel):
    _name = "payment.transaction.retry.lines"
    _description = "payment transaction retry lines"

    retry_id = fields.Many2one("payment.transaction.retry")
    invoice_id = fields.Many2one("account.move", readonly=True)
    partner_id = fields.Many2one("res.partner", related="invoice_id.partner_id")
    commercial_partner_id = fields.Many2one("res.partner", related="partner_id.commercial_partner_id")
    currency_id = fields.Many2one("res.currency", related="invoice_id.currency_id")
    amount_residual = fields.Monetary(related="invoice_id.amount_residual")
    amount_to_pay = fields.Monetary(compute="_compute_amount_to_pay", readonly=False)
    payment_token_id = fields.Many2one("payment.token", store=True, compute="_compute_payment_token_id", readonly=False)
    percentage = fields.Float(default=100)

    @api.depends("percentage")
    def _compute_amount_to_pay(self):
        for line in self:
            line.amount_to_pay = line.invoice_id.amount_residual * (line.percentage / 100)

    @api.onchange("amount_to_pay")
    def _onchange_amount_to_pay(self):
        for line in self:
            line.percentage = (line.amount_to_pay / line.invoice_id.amount_residual) * 100

    @api.depends("commercial_partner_id")
    def _compute_payment_token_id(self):
        for rec in self:
            token_list = self.env["payment.token"].search(
                [
                    ("company_id", "=", rec.retry_id.company_id.id),
                    "|",
                    ("partner_id", "child_of", rec.commercial_partner_id.id),
                    ("partner_id", "=", rec.commercial_partner_id.id),
                ]
            )
            if token_list:
                rec.payment_token_id = token_list.sorted(lambda x: x.create_date)[-1]
            else:
                rec.payment_token_id = False
