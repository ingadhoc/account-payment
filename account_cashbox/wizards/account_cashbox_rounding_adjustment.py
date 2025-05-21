from odoo import fields, models


class AccountCashboxRoundingAdjustment(models.TransientModel):
    _name = "account.cashbox.rounding.adjustment.wizard"
    _description = "Cashbox Rounding Adjustment"

    cashbox_session_id = fields.Many2one("account.cashbox.session")

    def action_create_journal_entries(self):
        """
        Create journal entries to adjust the rounding differences in the cashbox session.
        """

        # Create journal entries for each line with a rounding difference
        for line in self.cashbox_session_id.line_ids.filtered(lambda x: x.balance_difference != 0):
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
                            "debit": abs(min(line.balance_difference, 0.0)),
                            "credit": max(line.balance_difference, 0.0),
                            "account_id": (
                                line.journal_id.profit_account_id.id
                                if line.balance_difference > 0
                                else line.journal_id.loss_account_id.id
                            ),
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Cashbox Rounding Adjustment (Counterpart)",
                            "debit": max(line.balance_difference, 0.0),
                            "credit": abs(min(line.balance_difference, 0.0)),
                            "account_id": line.journal_id.default_account_id.id,
                        },
                    ),
                ],
            }
            move = self.env["account.move"].create(move_vals)
            move.action_post()

        self.cashbox_session_id.write({"state": "closed"})
        return True

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
