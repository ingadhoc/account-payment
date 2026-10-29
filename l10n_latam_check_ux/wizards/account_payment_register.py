from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        # The core builds one create command per wizard check, in the same order
        for command, check in zip(vals.get("l10n_latam_new_check_ids", []), self.l10n_latam_new_check_ids):
            command[2]["bank_id"] = check.bank_id.id
        return vals
