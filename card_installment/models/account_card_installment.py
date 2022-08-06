# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import timedelta

class AccountCardInstalment(models.Model):
    _name = 'account.card.instalment'
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
        min=1,
    )
    instalment = fields.Integer(
        string='instalment plan',
        min=1,
        help='Number of instalment'
    )
    coefficient = fields.Float(
        string='coefficient',
        help='Value to multiply the amount',
        default=1.0,
        digits='Instalment coefficient',
    )
    discount = fields.Float(
        string='discount',
        help='discount in amount'
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
        discount = (100 - self.discount) / 100
        return (amount * self.coefficient * discount) - amount

    def get_real_total(self, amount):
        self.ensure_one()
        discount = (100 - self.discount) / 100
        return amount * self.coefficient * discount

    def card_instalment_tree(self, amount_total):
        tree = {}
        for card in self.mapped('card_id'):
            tree[card.id] = card.map_card_values()

        for instalment in self:
            tree[instalment.card_id.id]['instalments'].append(instalment.map_instalment_values(amount_total))
        return tree

    def map_instalment_values(self, amount_total):

        self.ensure_one()
        discount = (100 - self.discount) / 100
        amount = amount_total * self.coefficient * discount
        return {
                    'id': self.id,
                    'name': self.name,
                    'instalment': self.instalment,
                    'coefficient': self.coefficient,
                    'discount': self.discount,
                    'bank_discount': self.bank_discount,
                    'divisor': self.divisor,
                    'base_amount': amount_total,
                    'amount': amount, 
                    'fee': amount - amount_total,
                }
