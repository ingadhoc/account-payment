##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class accountPaymentMethodLine(models.Model):

    _inherit = "account.payment.method.line"

    available_card_ids = fields.Many2many(
        'account.card',
        'account_method_line_card_rel',
        'method_id',
        'card_id',
        string='Cards',
    )
