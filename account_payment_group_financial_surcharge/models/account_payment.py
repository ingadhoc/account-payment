##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class AccountPayment(models.Model):

    _inherit = "account.payment"

    available_financing_plan_ids = fields.Many2many(string="Financing Plans Available", related='journal_id.financing_plan_ids')
    financing_plan_id = fields.Many2one(
        'account.financing.plan', store=True, readonly=False, compute='_compute_financing_plan')
    net_amount = fields.Monetary(compute='_computed_net_amount', inverse='_inverse_net_amount')

    @api.depends('amount')
    def _computed_net_amount(self):
        for rec in self:
            rec.net_amount = rec.amount * (1 - rec.financing_plan_id.surcharge_coefficient / 100.0)

    @api.onchange('financing_plan_id')
    def _onchange_financing_plan(self):
        """ no agregamos este onchange en el de _inverse_net_amount porque si no el amount se inicializa en cero.
        Eventualmente habria que mejorar esto. Se podria tal vez pasar el default por vista al net_amount tmb """
        for rec in self:
            rec._inverse_net_amount()

    @api.onchange('net_amount',)
    def _inverse_net_amount(self):
        for rec in self:
            rec.amount = rec.net_amount / (1 - rec.financing_plan_id.surcharge_coefficient / 100.0)

    @api.depends('available_financing_plan_ids', 'payment_type')
    def _compute_financing_plan(self):
        with_plan = self.filtered(lambda x: x.payment_type == 'inbound' and x._origin.available_financing_plan_ids)
        (self - with_plan).financing_plan_id = False
        for rec in with_plan:
            rec.financing_plan_id = rec._origin.available_financing_plan_ids[0]
