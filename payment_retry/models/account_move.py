from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"
    payment_state = fields.Selection(
        selection_add=[("electronic_pending", "Electronic payment")], ondelete={"electronic_pending": "cascade"}
    )
    status_in_payment = fields.Selection(
        selection_add=[("electronic_pending", "Electronic payment")], ondelete={"electronic_pending": "cascade"}
    )

    @api.depends("transaction_ids.state")
    def _compute_payment_state(self):
        super()._compute_payment_state()
        for rec in self.filtered(
            lambda x: x.payment_state == "not_paid"
            and {"pending", "authorized"}.intersection(set(x.transaction_ids.mapped("state")))
        ):
            rec.payment_state = "electronic_pending"
