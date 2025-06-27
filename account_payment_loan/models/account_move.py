from odoo import Command, _, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    loan_move_ids = fields.Many2many("account.move", "account_move_loan_rel", "move_id", "loan_move_id")
    last_interest_date_calculation = fields.Date(
        help="The date when the last interest calculation was performed for this move."
    )

    def action_register_loan(self):
        return self.line_ids.action_register_loan()

    def _get_total_debit(self, date=False):
        date = date if date else fields.Date.today()
        loan_surcharge = 0.0
        for rec in self.filtered(lambda x: not x.loan_move_ids):
            late_payment_interest = rec.company_id.late_payment_interest
            daily_interest = late_payment_interest / 30
            loan_account_id = rec.company_id.loan_journal_id.default_account_id

            for line_id in rec.line_ids.filtered(
                lambda x: x.account_id == loan_account_id
                and x.date_maturity
                and x.date_maturity < date
                and x.amount_residual
            ):
                last_interest_date_calculation = (
                    max(line_id.date_maturity, line_id.move_id.last_interest_date_calculation)
                    if line_id.move_id.last_interest_date_calculation
                    else line_id.date_maturity
                )
                diff_days = (
                    (date - last_interest_date_calculation).days
                    if (date - last_interest_date_calculation).days > 0
                    else 0
                )
                loan_surcharge += daily_interest * diff_days * line_id.amount_residual

        return loan_surcharge

    def create_financial_surchage_move(self, date=False):
        date = date if date else fields.Date.today()
        interest_move = self.env["account.move"]
        for rec in self:
            loan_surcharge = rec._get_total_debit(date)
            # intereses ganado  y perdidos
            loan_account_id = rec.company_id.loan_journal_id.default_account_id
            late_payment_interest_account_id = rec.company_id.account_late_payment_interest
            interest_move_data = {
                "partner_id": rec.partner_id.id,
                "journal_id": rec.company_id.loan_journal_id.id,
                "loan_move_ids": [Command.set(rec.ids)],
                "line_ids": [
                    Command.create(
                        {
                            "account_id": late_payment_interest_account_id.id,
                            "credit": loan_surcharge,
                            "name": _("Late payment interest"),
                            "currency_id": self.currency_id.id,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": loan_account_id.id,
                            "debit": loan_surcharge,
                            "name": _("Late payment interest"),
                            "currency_id": self.currency_id.id,
                        }
                    ),
                ],
            }
            interest_move |= self.env["account.move"].create(interest_move_data)
            rec.last_interest_date_calculation = date
        interest_move.action_post()
        return interest_move
