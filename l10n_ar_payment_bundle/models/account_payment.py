import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command, Domain


class AccountPayment(models.Model):
    _inherit = "account.payment"

    is_main_payment = fields.Boolean(compute="_compute_is_main_payment", store=True)
    main_payment_id = fields.Many2one("account.payment")
    link_payment_ids = fields.One2many(comodel_name="account.payment", inverse_name="main_payment_id")
    to_pay_move_line_ids = fields.Many2many(recursive=True)
    link_payments_total = fields.Monetary(
        currency_field="destination_currency_id",
        compute="_compute_link_payments_total",
    )
    partner_id = fields.Many2one(recursive=True)

    show_move_button = fields.Boolean(compute="_compute_show_move_button")
    warnings = fields.Json(
        compute="_compute_warnings",
    )
    payment_total = fields.Monetary(recursive=True)
    counterpart_currency_id = fields.Many2one(recursive=True)

    @api.constrains("amount", "is_main_payment")
    def _check_amount_in_main_payment(self):
        if self.filtered(lambda x: x.is_main_payment and x.amount != 0):
            raise ValidationError(_("The payment bundle amount always must be Zero"))

    @api.constrains("company_id", "main_payment_id", "link_payment_ids")
    def _check_bundle_company_consistency(self):
        for rec in self:
            if rec.main_payment_id and rec.company_id != rec.main_payment_id.company_id:
                raise ValidationError(_("The main payment and linked payment must belong to the same company."))

            if rec.link_payment_ids.filtered(lambda p: p.company_id != rec.company_id):
                raise ValidationError(_("The main payment and linked payments must belong to the same company."))

    def _check_bundle_currency_consistency(self):
        for rec in self.filtered("main_payment_id"):
            if rec.counterpart_currency_id != rec.main_payment_id.counterpart_currency_id:
                raise ValidationError(
                    _(
                        "The counterpart currency of a linked payment must match "
                        "the main payment's counterpart currency."
                    )
                )

    @api.depends("link_payment_ids.move_id")
    def _compute_show_move_button(self):
        for rec in self:
            rec.show_move_button = bool(rec.link_payment_ids.mapped("move_id"))

    @api.depends("payment_method_line_id")
    def _compute_is_main_payment(self):
        for rec in self:
            rec.is_main_payment = rec.payment_method_line_id.payment_method_id.code == "payment_bundle"

    @api.onchange("company_id", "partner_id")
    def _onchange_company_id(self):
        """si cambia partner o company por ahora limpiamos los pagos, eventualmente podríamos hacer partner_id computado
        y que, si cambia, se actualice. pero en tal caso habría que revisar otros campos que deberían recomputarse (cuentas, tokens, etc).
        """
        if self.link_payment_ids:
            self.link_payment_ids = [Command.clear()]

    @api.depends("link_payment_ids.payment_total")
    def _compute_payment_total(self):
        super()._compute_payment_total()
        for rec in self:
            rec.payment_total += sum(rec.link_payment_ids.mapped("payment_total"))

    @api.depends("main_payment_id.payment_difference")
    def _compute_to_pay_amount(self):
        for rec in self.filtered("main_payment_id"):
            rec.to_pay_amount = rec.main_payment_id.payment_difference
        super(AccountPayment, self - self.filtered("main_payment_id"))._compute_to_pay_amount()

    @api.depends("link_payment_ids.payment_total")
    def _compute_link_payments_total(self):
        """
        We added this computed field because we cannot modify counterpart_currency_amount,
        since as it is used into the journal entry.
        """
        main_payment_ids = self.filtered("is_main_payment")
        (self - main_payment_ids).link_payments_total = False
        for rec in main_payment_ids:
            rec.link_payments_total = sum(rec.link_payment_ids.mapped("payment_total"))

    @api.depends("use_payment_pro", "main_payment_id", "is_internal_transfer")
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for rec in self:
            if not rec.company_id:
                continue

            bundle_journal_id = rec.company_id._get_bundle_journal(rec.payment_type)
            journals = rec.available_journal_ids
            # If it's a linked payment remove only the bundle journal (any currency allowed)
            if rec.main_payment_id or rec.is_internal_transfer or not rec.use_payment_pro:
                journals = journals.filtered(lambda j: j._origin.id != bundle_journal_id)

            rec.available_journal_ids = journals

    def _compute_destination_journal_domain(self):
        super()._compute_destination_journal_domain()

        for rec in self.filtered(lambda p: p.is_internal_transfer and p.destination_company_id):
            bundle_journal_id = rec.company_id._get_bundle_journal(rec.payment_type)
            if not bundle_journal_id:
                continue

            rec.destination_journal_domain = Domain(rec.destination_journal_domain or []) & Domain(
                [("id", "!=", bundle_journal_id)]
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

    @api.depends("is_main_payment", "withholdings_amount")
    def _compute_amount(self):
        main_paments = self.filtered("is_main_payment")
        main_paments.amount = 0.0
        super(AccountPayment, self - main_paments)._compute_amount()

    @api.onchange("to_pay_move_line_ids")
    def _onchange_to_pay_lines_adjust_amount(self):
        """Para pagos principales del bundle, amount siempre debe ser 0; evita que
        la lógica de account_payment_pro intente ajustar el amount y dispare la
        constraint _check_amount_in_main_payment."""
        main_payments = self.filtered("is_main_payment")
        main_payments.amount = 0
        super(AccountPayment, self - main_payments)._onchange_to_pay_lines_adjust_amount()

    @api.onchange("withholdings_amount")
    def _onchange_withholdings(self):
        """dejamos este onchange además del compute_amount porque "le gana" en ejecución y, si cambian retenciones le asignaba un amount"""
        main_payments = self.filtered("is_main_payment")
        main_payments.amount = 0
        super(AccountPayment, self - main_payments)._onchange_withholdings()

    @api.depends("main_payment_id")
    def _compute_counterpart_rate(self):
        super(AccountPayment, self)._compute_counterpart_rate()
        # si tenemos main payment tomamos el counterpart_rate de ahí, no es necesario que el usuario lo ingrese en los pagos linkeados y así evitamos inconsistencias.
        # solo lo podemos hacer si la moneda del pago es en moneda de la cia ya que el rate del "bundle" siempre va a estar definido entre counterpart y moneda de la cia.
        for rec in self.filtered(lambda x: x.main_payment_id and x.currency_id == x.company_currency_id):
            rec.counterpart_rate = rec.main_payment_id.counterpart_rate

    @api.depends("main_payment_id")
    def _compute_accounting_rate(self):
        super(AccountPayment, self)._compute_accounting_rate()
        for rec in self.filtered(lambda x: x.main_payment_id and x.currency_id == x.counterpart_currency_id):
            # Si B = C en ambos pagos, tomamos la tasa forzada del main como
            # fuente de verdad para mantener counterpart_rate alineado.
            if rec.main_payment_id.counterpart_rate and rec.accounting_rate != rec.main_payment_id.counterpart_rate:
                rec.accounting_rate = rec.main_payment_id.counterpart_rate
            else:
                rec.accounting_rate = rec.main_payment_id.accounting_rate

    @api.depends("main_payment_id.counterpart_currency_id")
    def _compute_counterpart_currency_id(self):
        for rec in self.filtered("main_payment_id"):
            rec.counterpart_currency_id = rec.main_payment_id.counterpart_currency_id
        super(AccountPayment, self - self.filtered("main_payment_id"))._compute_counterpart_currency_id()

    def _compute_payment_difference(self):
        linked = self.filtered("main_payment_id")
        for rec in linked:
            # Usamos payment_total de cada linked (en B2/destination_currency_id) para que la
            # comparación con selected_debt y withholdings_amount —que también están en B2— sea
            # siempre en la misma moneda.  Cuando B1==B2 (caso normal), payment_total ==
            # counterpart_currency_amount, por lo que no hay regresión.  Cuando B1≠B2
            # (reconcile_on_company_currency), counterpart_currency_amount está en B1 y mezclaría
            # monedas; payment_total ya convierte A→C correctamente en ese branch.
            payments = rec.main_payment_id.link_payment_ids
            total_linked_in_b = sum(payments.mapped("payment_total"))
            rec.payment_difference = (
                abs(rec.main_payment_id.selected_debt)
                - total_linked_in_b
                - rec.main_payment_id.withholdings_amount
                - rec.main_payment_id.write_off_amount
            )
        super(AccountPayment, self - linked)._compute_payment_difference()

    @api.depends("payment_type", "link_payment_ids.payment_type")
    def _compute_warnings(self):
        for rec in self:
            warnings = {}
            if rec.state == "draft" and rec.is_main_payment and rec.link_payment_ids:
                linked_types = rec.link_payment_ids.mapped("payment_type")
                if len(set(linked_types)) > 1 or rec.payment_type not in linked_types:
                    warnings["payment_type_warning"] = {
                        "level": "info",
                        "message": _(
                            "The payment type of the main payment differs from one or more linked payments. Note that the main payment type only impacts withholdings and write-offs."
                        ),
                    }

            rec.warnings = warnings

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

        self._check_bundle_currency_consistency()

        res = super(AccountPayment, self).action_post()

        # Determine the starting suffix number based on the highest numeric
        # suffix already present in linked payment names (e.g. "PAY00003 (2)").
        existing_names = self.link_payment_ids.mapped("name")
        pattern = re.compile(r"\((\d+)\)\s*$")
        suffix_nums = [int(m.group(1)) for n in existing_names if n for m in [pattern.search(n)] if m]
        if suffix_nums:
            starting_suffix = max(suffix_nums)
        else:
            # Si no hay sufijos numéricos, arrancamos a partir de la cantidad de nombres no vacíos.
            starting_suffix = len([n for n in existing_names if n])

        next_num = starting_suffix + 1
        unnamed_payments = self.link_payment_ids.filtered(lambda p: not p.name)
        for payment in unnamed_payments:
            payment.name = f"{self.name} ({next_num})"
            next_num += 1

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
        # Only main bundle payments (is_main_payment, no main_payment_id) without write-off or withholdings skip journal entry.
        # Linked payments and regular payments always create journal entries, including write-off.
        return self.filtered(
            lambda x: x.is_main_payment and not x.main_payment_id and not (x.write_off_amount or x.withholdings_amount)
        )

    def _generate_journal_entry(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        super(AccountPayment, self - self._bypass_journal_entry())._generate_journal_entry(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
            line_ids=line_ids,
        )

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
        if self.filtered(lambda x: x.payment_method_line_id.payment_method_id.code == "payment_bundle"):
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

    def _compute_exchange_diff_move_ids(self):
        super()._compute_exchange_diff_move_ids()
        for rec in self.filtered("is_main_payment"):
            rec.exchange_diff_move_ids |= rec.link_payment_ids.mapped("exchange_diff_move_ids")
            rec.exchange_diff_move_count = len(rec.exchange_diff_move_ids)

    def _get_mached_payment(self):
        return super()._get_mached_payment() + self.link_payment_ids.ids
