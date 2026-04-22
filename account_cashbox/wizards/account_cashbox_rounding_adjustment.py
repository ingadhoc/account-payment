from odoo import api, fields, models


class AccountCashboxRoundingAdjustment(models.TransientModel):
    _name = "account.cashbox.rounding.adjustment.wizard"
    _description = "Cashbox Rounding Adjustment"

    cashbox_session_id = fields.Many2one("account.cashbox.session")
    forced_rate = fields.Float(
        help="Manually set the currency exchange rate for the adjustment",
        store=True,
        readonly=False,
    )
    force_rate = fields.Boolean(
        help="Check to manually set the exchange rate. If unchecked, the system will use the current currency exchange rate.",
    )
    has_currency = fields.Boolean(
        compute="_compute_has_currency",
        store=False,
    )

    def action_create_journal_entries(self):
        """
        Create journal entries to adjust the rounding differences in the cashbox session.
        """

        # Create journal entries for each line with a rounding difference
        for line in self.cashbox_session_id.line_ids.filtered(
            lambda x: x.balance_difference != 0 and x.require_cash_control
        ):
            currency = line.journal_id.currency_id or self.cashbox_session_id.company_id.currency_id
            if self.force_rate and self.forced_rate:
                negative_amount = abs(min(line.balance_difference, 0.0)) * self.forced_rate
                positive_amount = max(line.balance_difference, 0.0) * self.forced_rate
            elif currency != self.cashbox_session_id.company_id.currency_id:
                negative_amount = abs(min(line.balance_difference, 0.0)) / currency.rate
                positive_amount = max(line.balance_difference, 0.0) / currency.rate
            else:
                negative_amount = abs(min(line.balance_difference, 0.0))
                positive_amount = max(line.balance_difference, 0.0)

            move_vals = {
                "journal_id": line.journal_id.id,
                "date": fields.Date.today(),
                "cashbox_session_id": self.cashbox_session_id.id,
                "company_id": self.cashbox_session_id.company_id.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Cashbox Rounding Adjustment",
                            "debit": negative_amount,
                            "credit": positive_amount,
                            "account_id": (
                                line.journal_id.profit_account_id.id
                                if line.balance_difference > 0
                                else line.journal_id.loss_account_id.id
                            ),
                            "currency_id": currency.id,
                            "amount_currency": -line.balance_difference,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Cashbox Rounding Adjustment (Counterpart)",
                            "debit": positive_amount,
                            "credit": negative_amount,
                            "account_id": line.journal_id.default_account_id.id,
                            "currency_id": currency.id,
                            "amount_currency": line.balance_difference,
                        },
                    ),
                ],
            }
            move = self.env["account.move"].create(move_vals)
            move.action_post()

        self.cashbox_session_id.write({"state": "closed"})
        return True

    @api.depends("cashbox_session_id.line_ids.journal_id.currency_id", "cashbox_session_id.company_id.currency_id")
    def _compute_has_currency(self):
        for rec in self:
            comp_currency = rec.cashbox_session_id.company_id.currency_id
            rec.has_currency = any(
                j.currency_id and j.currency_id != comp_currency
                for j in rec.cashbox_session_id.line_ids.mapped("journal_id")
            )

    def action_close_without_entries(self):
        """
        Close the session without creating journal entries.
        """

        self.cashbox_session_id.write({"state": "closed"})
        return {"type": "ir.actions.act_window_close"}

    def action_open(self):
        """
        Open the wizard to adjust rounding differences in the cashbox session.
        """
        view_id = self.env.ref("account_cashbox.account_cashbox_rounding_adjustment_view_form").id
        return {
            "name": "Rounding Adjustment",
            "view_mode": "form",
            "view_id": view_id,
            "res_model": self._name,
            "type": "ir.actions.act_window",
            "target": "new",
            "context": self.env.context,
        }
