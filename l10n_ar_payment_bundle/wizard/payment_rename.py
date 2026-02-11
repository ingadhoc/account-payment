from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PaymentRenameWizard(models.TransientModel):
    _name = "payment.rename.wizard"
    _description = "Payment Rename Wizard"

    payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
        required=True,
    )
    new_name = fields.Char(
        required=True,
    )
    current_name = fields.Char(
        string="Current Name",
        related="payment_id.name",
        readonly=True,
    )

    @api.model
    def open_rename_wizard(self, payment_ids):
        """Server action method to open rename wizard"""
        payment = self.env["account.payment"].browse(payment_ids)

        return {
            "type": "ir.actions.act_window",
            "res_model": "payment.rename.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": payment.id},
        }

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        payment_id = None

        payment_id = self.env.context.get("active_id")

        if payment_id:
            payment = self.env["account.payment"].browse(payment_id)
            result["payment_id"] = payment_id
            result["new_name"] = payment.name
        return result

    def action_rename_payment(self):
        """Rename the payment"""
        if not self.new_name:
            raise UserError(_("Please enter a new name for the payment."))

        # Update the payment name for main and linked payments
        old_name = self.payment_id.name
        self.payment_id.write({"name": self.new_name})
        for i, payment in enumerate(self.payment_id.link_payment_ids):
            new_linked_name = f"{self.new_name} ({i + 1})"
            payment.name = new_linked_name
            payment.move_id.name = new_linked_name  # Update the move name to keep it in sync with the payment name

        # Log the change in chatter
        self.payment_id.message_post(
            body=_("Payment name changed from '%s' to '%s'") % (old_name, self.new_name),
            message_type="notification",
        )

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
