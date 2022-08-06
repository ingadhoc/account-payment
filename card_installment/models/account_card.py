from odoo import models, fields, api
import re 

class AccountCard(models.Model):
    _name = 'account.card'
    _description = 'Credit Card'

    name = fields.Char(
        'name',
        required=True,
    )
    instalment_product_id = fields.Many2one(
        'product.product',
        string='Product to invoice'
    )
    instalment_ids = fields.One2many(
        'account.card.instalment',
        'card_id',
        string='Instalments',
    )
    bin_ids = fields.One2many(
        'account.card.bin',
        'card_id',
        string='Bins'
    )
    company_id = fields.Many2one(
        'res.company',
        string='company',
        default=lambda self: self.env.company.id
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.model
    def get_card_by_bin(self, card_bin):
        card_bin = re.match(r'^([\s\d]+)$', card_bin)
        card_bin_id = self.env['account.card.bin'].search(
            [('name', 'in',
                  [int(card_bin[0:1]),
                   int(card_bin[0:2]),
                   int(card_bin[0:3]),
                   int(card_bin[0:4]),
                   int(card_bin[0:5]),
                   int(card_bin[0:6])
                   ]
            )],
            order='name desc',
            limit=1
        )
        if len(card_bin_id):
            return card_bin_id.card_id

    def map_card_values(self):

        self.ensure_one()
        return {
            'name': self.name,
            'id': self.id,
            'instalments': [],
            }
