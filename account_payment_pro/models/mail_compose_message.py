from odoo import _, api, fields, models


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    payment_background_send = fields.Boolean(compute="_compute_payment_background_send")

    @api.depends("model", "res_ids", "composition_mode")
    def _compute_payment_background_send(self):
        """True when this composer is sending the receipts of more payments than
        what we are willing to render inside the user request."""
        batch_size = self.env["account.payment"]._get_background_send_batch_size()
        for composer in self:
            res_ids = composer._evaluate_res_ids() or []
            composer.payment_background_send = bool(
                composer.model == "account.payment"
                and composer.composition_mode == "mass_mail"
                and len(res_ids) > batch_size
            )

    def action_send_mail(self):
        # EXTENDS 'mail': the user composes as usual (subject, body, attachments)
        # but for a big selection of payments the sending itself is queued: what
        # is expensive is rendering each receipt, not writing the email.
        if len(self) == 1 and self.payment_background_send:
            return self._action_send_payments_background()
        return super().action_send_mail()

    def _get_payment_background_send_values(self):
        """What the cron needs to send exactly the email the user composed."""
        self.ensure_one()
        return {
            "author_user_id": self.env.user.id,
            "author_id": self.author_id.id,
            "email_from": self.email_from,
            "subject": self.subject,
            "body": self.body,
            "email_layout_xmlid": self.email_layout_xmlid,
            "template_id": self.template_id.id,
            "attachment_ids": self.attachment_ids.ids,
        }

    def _action_send_payments_background(self):
        self.ensure_one()
        payments = self.env["account.payment"].browse(self._evaluate_res_ids())
        payments._queue_background_send(self._get_payment_background_send_values())
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "title": _("Sending receipts"),
                "message": _("The receipts are being sent in the background."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
