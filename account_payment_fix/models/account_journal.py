from odoo import fields, models, api
# from odoo.exceptions import ValidationError

class AccountPaymentAJ(models.Model):
    _inherit = "account.journal"

    at_least_one_inbound = fields.Boolean(compute='_methods_compute', store=True)
    at_least_one_outbound = fields.Boolean(compute='_methods_compute', store=True)

    @api.depends('inbound_payment_method_line_ids', 'outbound_payment_method_line_ids')
    def _methods_compute(self):
        for journal in self:
            journal.at_least_one_inbound = bool(len(journal.inbound_payment_method_line_ids))
            journal.at_least_one_outbound = bool(len(journal.outbound_payment_method_line_ids))