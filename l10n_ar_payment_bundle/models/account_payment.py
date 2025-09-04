from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    is_main_payment = fields.Boolean(compute="_compute_is_main_payment", store=True)
    main_payment_id = fields.Many2one("account.payment")
    link_payment_ids = fields.One2many(comodel_name="account.payment", inverse_name="main_payment_id")
    to_pay_move_line_ids = fields.Many2many(recursive=True)
    counterpart_exchange_rate = fields.Float(recursive=True)
    bundle_counterpart_currency_amount = fields.Monetary(
        currency_field="counterpart_currency_id",
        compute="_compute_bundle_counterpart_currency_amount",
    )
    partner_id = fields.Many2one(recursive=True)

    show_move_button = fields.Boolean(compute="_compute_show_move_button")

    @api.depends("link_payment_ids.move_id")
    def _compute_show_move_button(self):
        for rec in self:
            rec.show_move_button = bool(rec.link_payment_ids.mapped("move_id"))

    @api.depends("payment_method_line_id")
    def _compute_is_main_payment(self):
        for rec in self:
            rec.is_main_payment = rec.payment_method_line_id.payment_method_id.code == "payment_bundle"

    @api.onchange("is_main_payment")
    def _onchange_is_main_payment(self):
        self.filtered("is_main_payment").amount = 0

    @api.depends("link_payment_ids")
    def _compute_payment_total(self):
        super()._compute_payment_total()
        for rec in self:
            rec.payment_total += sum(rec.link_payment_ids.mapped("payment_total"))

    @api.depends("counterpart_currency_amount", "link_payment_ids.counterpart_currency_amount")
    def _compute_bundle_counterpart_currency_amount(self):
        """
        We added this computed field because we cannot modify counterpart_currency_amount,
        since as it is used into the journal entry.
        """
        main_payment_ids = self.filtered("is_main_payment")
        (self - main_payment_ids).bundle_counterpart_currency_amount = False
        for rec in main_payment_ids:
            rec.bundle_counterpart_currency_amount = float(rec.counterpart_currency_amount) + float(
                sum(rec.link_payment_ids.mapped("counterpart_currency_amount"))
            )

    @api.depends()
    def _compute_counterpart_currency_amount(self):
        main_payment_ids = self.filtered("is_main_payment")
        super(AccountPayment, self - main_payment_ids)._compute_counterpart_currency_amount()
        for rec in main_payment_ids:
            if rec.counterpart_currency_id and rec.counterpart_exchange_rate:
                rec.counterpart_currency_amount = (
                    rec.withholdings_amount + rec.write_off_amount
                ) / rec.counterpart_exchange_rate
            else:
                rec.counterpart_currency_amount = False

    @api.depends("use_payment_pro", "main_payment_id")
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for rec in self.filtered(lambda x: x.main_payment_id or not x.use_payment_pro and x.company_id):
            bundle_journal_id = rec.company_id._get_bundle_journal(rec.payment_type)
            rec.available_journal_ids = rec.available_journal_ids.filtered(
                lambda x: x._origin.id != bundle_journal_id and not x._origin.currency_id
            )

    @api.depends("main_payment_id.to_pay_move_line_ids")
    def _compute_to_pay_move_lines(self):
        with_main_payments = self.filtered("main_payment_id")
        for rec in with_main_payments:
            rec.to_pay_move_line_ids = rec.main_payment_id.to_pay_move_line_ids
        super(AccountPayment, self - with_main_payments)._compute_to_pay_move_lines()

    @api.depends("main_payment_id")
    def _compute_l10n_ar_withholding_line_ids(self):
        with_main_payments = self.filtered("main_payment_id")
        for rec in with_main_payments:
            rec.l10n_ar_withholding_line_ids = False
        super(AccountPayment, self - with_main_payments)._compute_l10n_ar_withholding_line_ids()

    # @api.depends("main_payment_id.counterpart_exchange_rate")
    # def _compute_counterpart_exchange_rate(self):
    #     with_main_payments = self.filtered(lambda x: x.main_payment_id and not x.counterpart_exchange_rate)
    #     for rec in with_main_payments:
    #         rec.counterpart_exchange_rate = rec.main_payment_id.counterpart_exchange_rate
    #     super(AccountPayment, self - with_main_payments)._compute_counterpart_exchange_rate()

    @api.constrains("amount", "is_main_payment")
    def _check_amount_in_main_payment(self):
        if self.filtered(lambda x: x.is_main_payment and x.amount != 0):
            raise ValidationError(_("The payment bundle amount always must be Zero"))

    @api.onchange("withholdings_amount")
    def _onchange_withholdings(self):
        main_payments = self.filtered("is_main_payment")
        main_payments.amount = 0
        for rec in self.filtered(lambda x: x.main_payment_id):
            amount = rec.amount + rec.payment_difference
            rec.amount = amount if amount > 0 else 0
        super(AccountPayment, self - main_payments)._onchange_withholdings()

    @api.onchange("counterpart_currency_id")
    def _onchange_counterpart_currency_id(self):
        self.mapped("link_payment_ids").counterpart_currency_id = self.counterpart_currency_id

    def _get_payment_bundles(self):
        main_payments = self.filtered("is_main_payment")
        bundles = super(AccountPayment, self - main_payments)._get_payment_bundles()
        for rec in main_payments:
            bundles[rec.id] += rec + rec.link_payment_ids
        return bundles

    def _select_bundle(self, bundles):
        self.ensure_one()
        if self.is_main_payment:
            return bundles.get(self.id)
        return super()._select_bundle(bundles)

    def action_post(self):
        if self.link_payment_ids and self.payment_method_code != "payment_bundle":
            self.link_payment_ids.unlink()

        if self.main_payment_id and not self.main_payment_id.name:
            raise ValidationError(_("The main payment must have a name before a linked payment can be posted."))

        res = super(AccountPayment, self).action_post()

        start_number = len(self.link_payment_ids.filtered(lambda x: x.name is not False))
        for i, payment in enumerate(self.link_payment_ids, start=start_number):
            if not payment.name:
                payment.name = f"{self.name} ({i + 1})"

        draft_linked = self.link_payment_ids.filtered(lambda x: x.state == "draft")
        if draft_linked:
            draft_linked.action_post()

        return res

    def action_draft(self):
        res = super(AccountPayment, self + self.link_payment_ids).action_draft()
        if self.main_payment_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.payment",
                "view_mode": "form",
                "res_id": self.id,
                "context": self.env.context,
            }
        return res

    def action_cancel(self):
        res = super(AccountPayment, self + self.link_payment_ids).action_cancel()
        return res

    def _bypass_journal_entry(self):
        return self.filtered(lambda x: x.is_main_payment and not (x.write_off_amount or x.withholdings_amount))

    def _generate_journal_entry(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        super(AccountPayment, self - self._bypass_journal_entry())._generate_journal_entry(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance, line_ids=line_ids
        )

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        res = super()._prepare_move_line_default_vals(write_off_line_vals=None, force_balance=None)
        if self.payment_method_code == "payment_bundle":
            bundle_account = self.payment_method_line_id.payment_account_id
            res = [line for line in res if not (line.get("account_id") == bundle_account.id)]
            for line in res:
                if "tax_repartition_line_id" in line:
                    tax_id = self.env["account.tax.repartition.line"].browse(line["tax_repartition_line_id"]).tax_id
                    if tax_id.l10n_ar_withholding_payment_type:
                        line["name"] = tax_id.name
        return res

    @api.depends("partner_id", "amount", "date", "payment_type")
    def _compute_duplicate_payment_ids(self):
        # Delete this when https://github.com/odoo/odoo/pull/210164 is merged
        # Bypass the duplicate payment check for main payments
        for rec in self:
            if rec.main_payment_id:
                rec.duplicate_payment_ids = False
            else:
                super()._compute_duplicate_payment_ids()

    def button_open_invoices(self):
        """Redirect the user to the invoice(s) paid by this payment.
        :return: An action on account.move.
        """
        self.ensure_one()
        if self.is_main_payment:
            return (
                (
                    self.invoice_ids
                    | self.reconciled_invoice_ids
                    | self.link_payment_ids.mapped("invoice_ids")
                    | self.link_payment_ids.mapped("reconciled_invoice_ids")
                )
                .with_context(create=False)
                ._get_records_action(
                    name=_("Paid Invoices"),
                )
            )
        return super().button_open_invoices()

    def button_open_bills(self):
        """Redirect the user to the bill(s) paid by this payment.
        :return:    An action on account.move.
        """
        self.ensure_one()
        if self.is_main_payment:
            action = {
                "name": _("Paid Bills"),
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "context": {"create": False},
            }
            reconciled_bill_ids = self.reconciled_bill_ids | self.link_payment_ids.mapped("reconciled_bill_ids")
            if len(reconciled_bill_ids) == 1:
                action.update(
                    {
                        "view_mode": "form",
                        "res_id": reconciled_bill_ids.id,
                    }
                )
            else:
                action.update(
                    {
                        "view_mode": "list,form",
                        "domain": [("id", "in", reconciled_bill_ids.ids)],
                    }
                )
            return action
        return super().button_open_bills()

    @api.depends()
    def _compute_stat_buttons_from_reconciliation(self):
        for rec in self:
            super()._compute_stat_buttons_from_reconciliation()
            if rec.is_main_payment:
                linked_payments = rec.link_payment_ids
                reconciled_invoice_ids = rec.reconciled_invoice_ids | linked_payments.mapped("reconciled_invoice_ids")
                reconciled_bill_ids = rec.reconciled_bill_ids | linked_payments.mapped("reconciled_bill_ids")
                rec.reconciled_invoices_count = len(reconciled_invoice_ids)
                rec.reconciled_bills_count = len(reconciled_bill_ids)

    def button_open_journal_entry(self):
        """Redirect the user to this payment journal.
        :return:    An action on account.move.
        """
        self.ensure_one()
        if self.is_main_payment:
            move_ids = self.move_id | self.link_payment_ids.mapped("move_id")
            return move_ids._get_records_action(
                name=_("Journal Entry"),
            )
        return super().button_open_journal_entry()

    @api.depends()
    def _compute_matched_amounts(self):
        super()._compute_matched_amounts()
        for rec in self.filtered("is_main_payment"):
            linked_payments = rec.link_payment_ids
            rec.matched_amount += sum(linked_payments.mapped("matched_amount"))
            rec.unmatched_amount = abs(rec.payment_total) - rec.matched_amount

        for rec in self - self.filtered("is_main_payment"):
            rec.unmatched_amount = 0.0

    @api.depends("move_id.line_ids")
    def _compute_matched_move_line_ids(self):
        super()._compute_matched_move_line_ids()
        for rec in self.filtered("is_main_payment"):
            rec.matched_move_line_ids |= rec.link_payment_ids.mapped("matched_move_line_ids")

    def _get_mached_payment(self):
        return super()._get_mached_payment() + self.link_payment_ids.ids

    @api.depends("main_payment_id.partner_id")
    def _compute_partner_id(self):
        super()._compute_partner_id()
        for rec in self.filtered("main_payment_id"):
            rec.partner_id = rec.main_payment_id.partner_id

    def _compute_payment_difference(self):
        for rec in self.filtered("main_payment_id"):
            payments = rec.main_payment_id.link_payment_ids
            amount_outbound = sum(
                payments.filtered(lambda p: p.payment_type == "outbound").mapped("amount_company_currency_signed")
            )
            amount_inbound = sum(
                payments.filtered(lambda p: p.payment_type == "inbound").mapped("amount_company_currency_signed")
            )
            amount_payments = abs(amount_inbound + amount_outbound)

            rec.payment_difference = (
                rec.main_payment_id.selected_debt
                - amount_payments
                - rec.main_payment_id.withholdings_amount
                - rec.main_payment_id.write_off_amount
            )

        for rec in self - self.filtered("main_payment_id"):
            return super()._compute_payment_difference()
