# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import float_is_zero

from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class PosMakePayment(models.TransientModel):
    _inherit = "pos.make.payment"

    card_id = fields.Many2one(
        "account.card", string="Card", related="payment_method_id.card_id"
    )
    instalment_id = fields.Many2one("account.card.installment", string="Instalment plan")
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
