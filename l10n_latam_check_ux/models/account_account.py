from odoo import models


class AccountAccount(models.Model):
    _inherit = "account.account"

    def write(self, vals):
        res = super().write(vals)
        if "reconcile" in vals:
            # sudo: the account is shared across the whole company hierarchy, so the stored
            # issue_state of checks living in branches the user has not enabled must be
            # recomputed as well.
            checks = (
                self.env["l10n_latam.check"]
                .sudo()
                .search(
                    [
                        ("outstanding_line_id.account_id", "in", self.ids),
                    ]
                )
            )
            checks._compute_issue_state()
        return res
