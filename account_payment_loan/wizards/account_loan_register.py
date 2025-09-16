from dateutil.relativedelta import relativedelta
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountLoanRegister(models.TransientModel):
    _name = "account.loan.register"
    _description = "Account Loan Register"

    refinancial_loan_move_ids = fields.Many2many(
        comodel_name="account.move",
        string="Refinancial Loan",
    )
    company_id = fields.Many2one("res.company", store=True, compute="_compute_company_id")
    currency_id = fields.Many2one("res.currency", store=True, compute="_compute_currency_id")
    partner_id = fields.Many2one("res.partner", store=True, compute="_compute_partner_id")
    amount = fields.Monetary()
    move_line_ids = fields.Many2many(
        comodel_name="account.move.line",
        store=True,
        string="Move Lines",
        required=True,
        domain=[("reconciled", "=", False)],
    )

    card_id = fields.Many2one(
        comodel_name="account.card",
        string="Card",
        domain=[("is_loan", "=", True)],
        compute="_compute_card_id",
        store=True,
        required=True,
        readonly=False,
    )

    installment_id = fields.Many2one(
        "account.card.installment",
        string="Installment plan",
        compute="_compute_installment_id",
        store=True,
        readonly=False,
    )
    is_invoiceable = fields.Boolean(
        help="If checked, se creara una ND sino un asiento contable",
    )

    loan_description = fields.Html(compute="_compute_loan_description")

    note = fields.Text(compute="_compute_note", readonly=False, string="Internal Note")

    @api.depends("installment_id", "amount")
    def _compute_note(self):
        for record in self.filtered("installment_id"):
            record.note = record.installment_id.map_installment_values(record.amount).get("description")

    def _get_loan_instalemnts(self):
        installments = []
        amount_total = self.amount * self.installment_id.surcharge_coefficient
        for divisor in range(1, self.installment_id.divisor + 1):
            date_maturity = fields.Date.today() + relativedelta(months=divisor)
            if self.card_id.loan_due_method == "next_day_number":
                date_maturity = date_maturity.replace(day=self.card_id.due_day)
            installments.append(
                {
                    "divisor": divisor,
                    "amount": amount_total / self.installment_id.divisor,
                    "date_maturity": date_maturity,
                }
            )
        return installments

    @api.depends("installment_id", "amount")
    def _compute_loan_description(self):
        html = '<table class="table table-sm  table-striped">'
        html += _("<tr><th>Installment</th><th>Date due</th><th>Amount</th></tr>")
        for installment in self._get_loan_instalemnts():
            html += _("<tr><td>Fee N. %s</td><td>%s</td><td>%s</td></tr>") % (
                installment["divisor"],
                fields.Date.to_string(installment["date_maturity"]),
                self.currency_id.format(installment["amount"]),
            )
        html += "<table>"
        self.loan_description = html

    @api.depends("move_line_ids")
    def _compute_currency_id(self):
        for record in self:
            record.currency_id = record.move_line_ids[0].currency_id

    @api.depends("move_line_ids")
    def _compute_partner_id(self):
        for record in self:
            record.partner_id = record.move_line_ids[0].partner_id

    @api.depends("move_line_ids")
    def _compute_company_id(self):
        for record in self:
            record.company_id = record.move_line_ids[0].company_id

    @api.depends("card_id")
    def _compute_card_id(self):
        for record in self:
            record.card_id = self.env["account.card"].search([], limit=1)

    @api.depends("card_id.installment_ids")
    def _compute_installment_id(self):
        for record in self:
            if len(record.card_id.installment_ids.ids) > 0:
                record.installment_id = record.card_id.installment_ids.ids[0]
            else:
                record.installment_id = False

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if self.env.context.get("refinancial_loan_move_ids"):
            loan_move_ids = self.env["account.move"].browse(self.env.context.get("refinancial_loan_move_ids")).exists()
            res["refinancial_loan_move_ids"] = [Command.set(loan_move_ids.ids)]
            amls = loan_move_ids.mapped("line_ids").filtered("debit")
            res["move_line_ids"] = [Command.set(amls.ids)]
            res["amount"] = loan_move_ids._get_total_debit() + sum(amls.mapped("amount_residual"))

        elif self.env.context.get("active_ids"):
            amls = self.env["account.move.line"].browse(self.env.context.get("active_ids", [])).filtered("debit")
            res["move_line_ids"] = [Command.set(amls.ids)]
            res["amount"] = sum(amls.mapped("amount_residual"))
        if not res.get("move_line_ids") or res.get("amount", 0) <= 0:
            raise UserError(_("No valid lines or amount found."))
        return res

    def _prepare_loan_move_data(self):
        amount_total = self.amount * self.installment_id.surcharge_coefficient
        loan_account = self.company_id.loan_journal_id.default_account_id
        loan_move_data = {
            "partner_id": self.partner_id.id,
            "journal_id": self.company_id.loan_journal_id.id,
            "line_ids": [],
        }
        debit_total = credit_total = 0.0
        if self.is_invoiceable:
            credit_total += self.currency_id.round(amount_total)
            loan_move_data["line_ids"].append(
                Command.create(
                    {
                        "account_id": self.move_line_ids[0].account_id.id,
                        "credit": amount_total,
                        "name": _("credit"),
                        "currency_id": self.currency_id.id,
                    }
                ),
            )
        else:
            credit_total += self.currency_id.round(self.amount)
            loan_move_data["line_ids"].append(
                Command.create(
                    {
                        "account_id": self.move_line_ids[0].account_id.id,
                        "credit": self.amount,
                        "name": _("credit"),
                        "currency_id": self.currency_id.id,
                    }
                )
            )
            late_payment_interest_account_id = self.company_id.account_late_payment_interest
            credit_total += self.currency_id.round(amount_total - self.amount)
            loan_move_data["line_ids"].append(
                Command.create(
                    {
                        "account_id": late_payment_interest_account_id.id,
                        "credit": amount_total - self.amount,
                        "name": _("Financial Surcharge"),
                        "currency_id": self.currency_id.id,
                    }
                )
            )

        for installment in self._get_loan_instalemnts():
            debit_total += self.currency_id.round(installment["amount"])
            loan_move_data["line_ids"].append(
                Command.create(
                    {
                        "account_id": loan_account.id,
                        "debit": installment["amount"],
                        "name": _("fee N. %s due date %s")
                        % (installment["divisor"], fields.Date.to_string(installment["date_maturity"])),
                        "date_maturity": installment["date_maturity"],
                        "currency_id": self.currency_id.id,
                    }
                )
            )
        compare_amounts = self.currency_id.compare_amounts(debit_total, credit_total)
        if compare_amounts:
            loan_move_data["line_ids"].append(
                Command.create(
                    {
                        "account_id": self.env.ref(f"account.{self.company_id.id}_account_loan_round").id,
                        "balance": credit_total - debit_total,
                        "name": _("Rounding"),
                        "currency_id": self.currency_id.id,
                    }
                )
            )

        return loan_move_data

    def action_register_loan(self):
        amount_total = self.amount * self.installment_id.surcharge_coefficient

        loan_move_data = self._prepare_loan_move_data()
        loan_move = self.env["account.move"].create(loan_move_data)
        loan_move.action_post()
        move_id = self.move_line_ids.mapped("move_id")[0]
        debit_note_id = self.env["account.move"]

        if self.is_invoiceable and not self.refinancial_loan_move_ids:
            product = self.company_id.product_surcharge_id
            taxes = product.taxes_id.filtered(lambda t: t.company_id.id == self.company_id.id)
            total_excluded = taxes.with_context(force_price_include=True).compute_all(
                price_unit=amount_total - self.amount,
                currency=move_id.currency_id,
                quantity=1,
                product=product.sudo(),
                partner=move_id.partner_id,
            )["total_excluded"]

            if move_id.state != "draft":
                move_debit_note_wiz = (
                    self.env["account.debit.note"]
                    .with_context(active_model="account.move", active_ids=move_id.ids)
                    .create(
                        {
                            "date": fields.Date.context_today(self),
                            "reason": "Financial Surcharge",
                        }
                    )
                )
                debit_note_id = self.env["account.move"].browse(move_debit_note_wiz.create_debit().get("res_id"))

                debit_note_id.line_ids = [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": total_excluded,
                            "tax_ids": [(6, 0, taxes.ids)],
                        }
                    )
                ]
                debit_note_id.action_post()

            else:
                move_id.line_ids = [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": total_excluded,
                            "tax_ids": [(6, 0, taxes.ids)],
                        }
                    )
                ]

        counterpart_line = loan_move.line_ids.filtered(lambda x: x.account_id == self.move_line_ids[0].account_id)
        debit_lines = (
            (debit_note_id + move_id)
            .mapped("line_ids")
            .filtered(lambda x: x.account_id.account_type == "asset_receivable")
        )
        (counterpart_line + debit_lines).reconcile()
        body = _(
            """A new loan %(loan_move)s was created
        %(loan_description)s
        %(note)s
        """,
            loan_move=loan_move._get_html_link(title=loan_move.display_name),
            loan_description=self.loan_description,
            note=self.note,
        )

        move_id.message_post(body=body)

    def action_refinancial_loan(self):
        loan_move_data = self._prepare_loan_move_data()
        loan_move = self.env["account.move"].create(loan_move_data)
        loan_move.action_post()
        counterpart_line = loan_move.line_ids.filtered(
            lambda x: x.account_id == self.move_line_ids[0].account_id and x.credit > 0
        )
        (counterpart_line + self.move_line_ids).reconcile()
        body = _(
            """This %(loan_move)s is refinancial
        %(loan_description)s
        %(note)s
        """,
            loan_move=loan_move._get_html_link(title=loan_move.display_name),
            loan_description=self.loan_description,
            note=self.note,
        )

        self.refinancial_loan_move_ids._message_log_batch(bodies={x.id: body for x in self.refinancial_loan_move_ids})
