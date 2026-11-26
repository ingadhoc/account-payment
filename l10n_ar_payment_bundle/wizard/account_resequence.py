from odoo import _, api, models
from odoo.exceptions import UserError


class AccountResequenceWizard(models.TransientModel):
    _inherit = "account.resequence.wizard"

    @api.model
    def default_get(self, fields):
        move_ids = self.env["account.move"].browse(self.env.context.get("active_ids", []))
        if any(move_ids.payment_ids.main_payment_id):
            raise UserError(
                _("You cannot resequence moves linked to a bundle payment. Please resequence the payment instead.")
            )
        return super().default_get(fields)
