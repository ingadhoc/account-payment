from odoo import _, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def action_register_loan(self, ctx=None):
        """Open the account.payment.register wizard to pay the selected journal items.
        :return: An action opening the account.payment.register wizard.
        """
        context = {
            "active_model": "account.move.line",
            "active_ids": self.ids,
        }
        if ctx:
            context.update(ctx)
        return {
            "name": _("Register Loan"),
            "res_model": "account.loan.register",
            "view_mode": "form",
            "views": [[False, "form"]],
            "context": context,
            "target": "new",
            "type": "ir.actions.act_window",
        }
