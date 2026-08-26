from odoo import _, fields, models


class ElectronicPaymentPendingConfirm(models.TransientModel):
    _name = "electronic.payment.pending.confirm"
    _description = "Confirm a manual payment while an electronic payment is on course"

    move_ids = fields.Many2many("account.move", required=True)

    def action_confirm(self):
        self.ensure_one()
        for move in self.move_ids:
            move.message_post(
                body=_(
                    "The payment is being registered manually while the electronic payment %s is still on course.",
                    ", ".join(move._get_pending_transactions().mapped("reference")),
                ),
                subtype_xmlid="mail.mt_note",
            )
        return self.move_ids.with_context(skip_electronic_pending_check=True).action_force_register_payment()
