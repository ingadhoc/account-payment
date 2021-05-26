##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class AccountPayment(models.Model):

    _inherit = "account.payment"

    available_financing_plans_ids = fields.Many2many(
        related='journal_id.financing_plans_ids')
    financing_plan_id = fields.Many2one('account.financing_plans')
    net_amount = fields.Float(
        compute='_computed_net_amount',
        inverse='set_net_amount',
    )

    @api.depends('amount', 'financing_plan_id')
    def _computed_net_amount(self):
        for rec in self:
            rec.net_amount = rec.amount - (rec.amount * (rec.financing_plan_id.surcharge_coefficient / 100))

    @api.onchange('net_amount')
    def set_net_amount(self):
        for rec in self:
            rec.amount = (rec.net_amount * ((rec.financing_plan_id.surcharge_coefficient/100) + 1))
