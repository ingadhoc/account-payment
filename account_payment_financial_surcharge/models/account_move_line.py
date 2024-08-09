from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def action_register_payment(self):
        res = super().action_register_payment()
        res['context']['default_net_amount'] = res['context']['default_amount']
        return res
