from odoo import fields, models


class AccountCashbox(models.Model):
    _inherit = "account.cashbox"

    journal_ids = fields.Many2many(
        domain=[
            ("type", "in", ["bank", "cash"]),
            "!",
            "|",
            ("inbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
            ("outbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
        ],
    )
