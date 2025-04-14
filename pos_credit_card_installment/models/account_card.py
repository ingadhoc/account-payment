##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class AccountCard(models.Model):
    _inherit = 'account.card'
    _description = 'Credit Card'

    card_logo = fields.Binary(
        string="Card logo",
        attachment=True,
    )
    card_type = fields.Selection(
        [("credit", "credit"), ("debit", "debit")],
        required=True,
    )
