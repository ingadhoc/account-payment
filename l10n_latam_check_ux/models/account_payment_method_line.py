from odoo import _, models
from odoo.exceptions import UserError


class AccountPaymentMethodLine(models.Model):
    _inherit = "account.payment.method.line"

    def unlink(self):
        """Prevenir eliminación si hay cheques pendientes asociados."""
        for rec in self:
            if rec.code in ["new_third_party_checks", "own_checks", "issued_checks"]:
                checks = (
                    self.env["l10n_latam.check"]
                    .sudo()
                    .search([("current_journal_id", "=", rec.journal_id.id)], limit=1)
                )
                if checks:
                    raise UserError(
                        _(
                            "You cannot delete this payment method because it has "
                            "associated checks. You must first delete or reassign "
                            "all related checks."
                        )
                    )
        return super().unlink()
