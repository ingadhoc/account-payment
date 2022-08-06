from odoo import models, fields


class AccountCard(models.Model):
    _name = 'account.card.bin'
    _description = 'Card bin'

    name = fields.Integer(
        'bin',
        required=True,
    )
    card_id = fields.Many2one(
        'account.card',
        string='Card',
        required=True,
    )