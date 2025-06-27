from odoo import Command, _, api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    loan_surcharge = fields.Monetary(
        compute="_compute_loan_surcharge",
        store=True,
        readonly=False,
        tracking=True,
    )
    is_loan_payment = fields.Boolean(compute="_compute_is_loan_payment", store=True)

    @api.depends("to_pay_move_line_ids")
    def _compute_is_loan_payment(self):
        for rec in self:
            loan_account_id = rec.company_id.loan_journal_id.default_account_id
            rec.is_loan_payment = rec.to_pay_move_line_ids.filtered(
                lambda x: x.account_id == loan_account_id and not x.move_id.loan_move_ids
            ).exists()

    @api.depends("date", "to_pay_move_line_ids", "state")
    def _compute_loan_surcharge(self):
        for rec in self.filtered(lambda x: x.state == "draft"):
            loan_surcharge = 0.0
            late_payment_interest = rec.company_id.late_payment_interest
            daily_interest = late_payment_interest / 30
            loan_account_id = rec.company_id.loan_journal_id.default_account_id
            for loan_id in rec.to_pay_move_line_ids.filtered(lambda x: x.account_id == loan_account_id).mapped(
                "move_id"
            ):
                for line_id in loan_id.line_ids.filtered(
                    lambda x: x.date_maturity and x.date_maturity < rec.date and x.amount_residual
                ):
                    last_interest_date_calculation = (
                        max(line_id.date_maturity, line_id.move_id.last_interest_date_calculation)
                        if line_id.move_id.last_interest_date_calculation
                        else line_id.date_maturity
                    )
                    diff_days = (
                        (rec.date - last_interest_date_calculation).days
                        if (rec.date - last_interest_date_calculation).days > 0
                        else 0
                    )
                    loan_surcharge += daily_interest * diff_days * line_id.amount_residual

            rec.loan_surcharge = loan_surcharge

    def action_post(self):
        for rec in self.filtered(lambda p: p.is_loan_payment):
            if rec.loan_surcharge:
                # intereses ganado  y perdidos
                loan_account_id = rec.company_id.loan_journal_id.default_account_id
                late_payment_interest_account_id = rec.company_id.account_late_payment_interest
                loan_base_move_ids = (
                    rec.to_pay_move_line_ids.filtered(lambda x: x.account_id == loan_account_id)
                    .mapped("move_id")
                    .filtered(lambda x: not x.loan_move_ids)
                )
                interest_move_data = {
                    "partner_id": rec.partner_id.id,
                    "loan_move_ids": [Command.set(loan_base_move_ids.ids)],
                    "journal_id": rec.company_id.loan_journal_id.id,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": late_payment_interest_account_id.id,
                                "credit": rec.loan_surcharge,
                                "name": _("Late payment interest"),
                                "currency_id": self.currency_id.id,
                            }
                        ),
                        Command.create(
                            {
                                "account_id": loan_account_id.id,
                                "debit": rec.loan_surcharge,
                                "name": _("Late payment interest"),
                                "currency_id": self.currency_id.id,
                            }
                        ),
                    ],
                }
                interest_move = self.env["account.move"].create(interest_move_data)
                interest_move.action_post()
                # TODO unificar ??
                # interest_moves = self.env["account.move"].create_financial_surchage_move(rec.loan_surcharge)

                loan_move_ids = rec.to_pay_move_line_ids.filtered(lambda x: x.account_id == loan_account_id).mapped(
                    "move_id"
                )
                loan_move_ids.last_interest_date_calculation = rec.date
                loan_surcharge_line = interest_move.line_ids.filtered(lambda x: x.account_id == loan_account_id)
                rec.to_pay_move_line_ids = [Command.link(loan_surcharge_line.id)]

        return super().action_post()

    def _reconcile_after_post(self):
        for rec in self.filtered(lambda x: x.company_id.use_payment_pro and not x.is_internal_transfer):
            counterpart_aml = rec.mapped("move_id.line_ids").filtered(
                lambda r: not r.reconciled and r.account_id.account_type in self._get_valid_payment_account_types()
            )
            debt_aml = rec.to_pay_move_line_ids.filtered(lambda x: x.move_id.loan_move_ids)
            if counterpart_aml and debt_aml:
                (counterpart_aml + (debt_aml)).reconcile()
        super()._reconcile_after_post()
