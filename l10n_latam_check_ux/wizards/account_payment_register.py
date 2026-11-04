##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        # The wizard creates the payment with its journal entry, already in process, so action_post
        # does not see it as a draft and does not set the operation date.
        if self.l10n_latam_new_check_ids or self.l10n_latam_move_check_ids:
            vals["l10n_latam_move_check_ids_operation_date"] = self.env["account.payment"]._get_checks_operation_date(
                self.l10n_latam_move_check_ids
            )
        # The core builds one create command per wizard check, in the same order
        for command, check in zip(vals.get("l10n_latam_new_check_ids", []), self.l10n_latam_new_check_ids):
            command[2]["bank_id"] = check.bank_id.id
        return vals
