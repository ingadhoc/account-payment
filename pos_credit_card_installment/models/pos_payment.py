from odoo import api, fields, models, _
from odoo.tools import formatLang

import logging

_logger = logging.getLogger(__name__)


class PosPayment(models.Model):

    _inherit = "pos.payment"

    card_id = fields.Many2one("account.card", string="Card")

    instalment_id = fields.Many2one("account.card.installment", string="Instalment plan")
    instalment = fields.Integer(
        string="instalment plan", related="instalment_id.installment"
    )
    card_type = fields.Selection(
        [("credit", "credit"), ("debit", "debit")]
    )

    magnet_bar = fields.Char("magnet bar")
    card_number = fields.Char("Card number")
    tiket_number = fields.Char("Tiket number")
    lot_number = fields.Char("Lot number")
    fee = fields.Float(
        string="Fee",
        default=0,
    )
    total_amount = fields.Float(
        string="total amount",
        default=0,
    )
    discount = fields.Float(
        string="discount",
        help="discount in %",
        related="instalment_id.bank_discount",
    )
    bank_discount = fields.Float(
        string="Bank discount",
        help="Bank discount in %",
        related="instalment_id.bank_discount",
    )
