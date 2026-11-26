from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    cashbox_session_id = fields.Many2one(
        "account.cashbox.session",
        string="Cashbox Session",
        help="Cashbox session associated with this move.",
        readonly=True,
    )
