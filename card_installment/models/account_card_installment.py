##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, _


class AccountCardInstallment(models.Model):
    _name = 'account.card.installment'
    _description = 'amount to add for collection in installments'

    card_id = fields.Many2one(
        'account.card',
        string='Card',
        required=True,
    )
    name = fields.Char(
        'Fantasy name',
        default='/'
    )
    divisor = fields.Integer(
        string='Divisor',
    )
    installment = fields.Integer(
        string='installment plan',
        help='Number of installment'
    )
    surcharge_coefficient = fields.Float(
        string='coefficient',
        default=1.0,
        digits='Installment coefficient',
        help='Coeficiente con iva incluido'
    )
    bank_discount = fields.Float(
        string='bank discount',
        help='Bank discount'
    )
    active = fields.Boolean(
        'Active',
        default=True
    )

    def name_get(self):
        result = []
        for record in self:
            name = record.card_id.name + ' ' + record.name
            result.append((record.id, name))
        return result

    def get_fees(self, amount):
        self.ensure_one()
        return amount * self.surcharge_coefficient - amount

    def get_real_total(self, amount):
        self.ensure_one()
        return amount * self.surcharge_coefficient

    def card_installment_tree(self, amount_total):
        tree = {}
        for card in self.mapped('card_id'):
            tree[card.id] = card.map_card_values()

        for installment in self:
            tree[installment.card_id.id]['installments'].append(installment.map_installment_values(amount_total))
        return tree

    def map_installment_values(self, amount_total):
        self.ensure_one()
        amount = amount_total * self.surcharge_coefficient
        return {
                    'id': self.id,
                    'name': self.name,
                    'installment': self.installment,
                    'coefficient': self.surcharge_coefficient,
                    'bank_discount': self.bank_discount,
                    'divisor': self.divisor,
                    'base_amount': amount_total,
                    'amount': amount,
                    'fee': amount - amount_total,
                    'description': _('%s installment of %.2f (total %.2f)' % (self.divisor, amount / self.divisor, amount))
                }
