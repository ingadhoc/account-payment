##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class AccountPayment(models.Model):

    _inherit = "account.payment"

    available_financing_plans_ids = fields.Many2many(related='journal_id.financing_plans_ids')
    financing_plan_id = fields.Many2one(
        'account.financing_plans', store=True, readonly=False, compute='_compute_financing_plan')
    surcharged_amount = fields.Monetary(compute='_computed_surcharged_amount')

    @api.depends('available_financing_plans_ids', 'payment_type')
    def _compute_financing_plan(self):
        with_plan = self.filtered(lambda x: x.payment_type == 'inbound' and x._origin.available_financing_plans_ids)
        (self - with_plan).financing_plan_id = False
        for rec in with_plan:
            rec.financing_plan_id = rec._origin.available_financing_plans_ids[0]

    @api.depends('amount', 'financing_plan_id')
    def _computed_surcharged_amount(self):
        surcharged_payments = self.filtered('financing_plan_id')
        (self - surcharged_payments).surcharged_amount = False
        for rec in surcharged_payments:
            rec.surcharged_amount = rec.amount / (1 - rec.financing_plan_id.surcharge_coefficient / 100.0)
