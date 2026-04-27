from odoo import models


class AccountAccount(models.Model):
    _inherit = "account.account"

    def write(self, vals):
        res = super().write(vals)
        if "reconcile" in vals:
            checks = self.env["l10n_latam.check"].search(
                [
                    ("outstanding_line_id.account_id", "in", self.ids),
                ]
            )
            checks._compute_issue_state()
        return res
