##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class AccountCard(models.Model):
    _name = 'account.card'
    _description = 'Credit Card'

    name = fields.Char(
        'name',
        required=True,
    )
    installment_ids = fields.One2many(
        'account.card.installment',
        'card_id',
        string='Installments',
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

    def map_card_values(self):

        self.ensure_one()
        return {
            'name': self.name,
            'id': self.id,
            'installments': [],
            }
