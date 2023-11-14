# -*- coding: utf-8 -*-

from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


class AccountCardInstallment(models.Model):
    _inherit = "account.card.installment"

    card_type = fields.Selection(
        [("credit", "credit"), ("debit", "debit")], related="card_id.card_type"
    )

    financial_surcharge = fields.Float(string='Financial charge')
