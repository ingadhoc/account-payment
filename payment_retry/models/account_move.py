from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    status_in_payment = fields.Selection(
        selection_add=[("electronic_pending", "Electronic payment")], ondelete={"electronic_pending": "cascade"}
    )
    has_pending_transaction = fields.Boolean(
        compute="_compute_has_pending_transaction",
        help="Technical field to know if there is an electronic payment on course for this invoice.",
    )

    def _get_pending_transactions(self):
        """Return the electronic payments on course, the ones that could still pay these invoices.

        Payment transactions are only readable by settings users, hence the sudo.
        """
        return self.sudo().transaction_ids.filtered(lambda tx: tx.state in ("pending", "authorized"))

    @api.depends("transaction_ids.state")
    def _compute_has_pending_transaction(self):
        for rec in self:
            rec.has_pending_transaction = bool(rec._get_pending_transactions())

    @api.depends("has_pending_transaction", "payment_state", "state", "is_move_sent")
    def _compute_status_in_payment(self):
        super()._compute_status_in_payment()
        for rec in self.filtered(
            lambda x: x.has_pending_transaction and x.state == "posted" and x.payment_state == "not_paid"
        ):
            rec.status_in_payment = "electronic_pending"

    def action_force_register_payment(self):
        """Warn before registering a payment by hand when an electronic payment is on course:
        if the customer also pays it online, the invoice ends up being paid twice.

        The check goes here and not on action_register_payment because that one only validates and
        delegates here, and because some modules point the invoice button straight to this method.
        """
        if self.env.context.get("skip_electronic_pending_check") or not self.filtered("has_pending_transaction"):
            return super().action_force_register_payment()
        return {
            "type": "ir.actions.act_window",
            "name": _("Electronic payment on course"),
            "res_model": "electronic.payment.pending.confirm",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_ids": self.ids},
        }

    def _has_to_be_paid(self):
        self.ensure_one()
        if self.has_pending_transaction:
            return False
        return super()._has_to_be_paid()
