from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def action_register_payment(self, ctx=None):
        action = super().action_register_payment(ctx=ctx)
        # Si el diario por defecto es bundle
        journal = self.env["account.journal"].search(
            [
                *self.env["account.journal"]._check_company_domain(self.company_id),
                ("type", "in", ["bank", "cash", "credit"]),
            ],
            limit=1,
        )

        if "payment_bundle" in (
            journal.inbound_payment_method_line_ids + journal.outbound_payment_method_line_ids
        ).mapped("code"):
            action.setdefault("context", {})["default_amount"] = 0
        return action
