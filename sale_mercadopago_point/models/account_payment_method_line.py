from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = "account.payment.method.line"

    mp_point_store_id = fields.Char(
        string='MercadoPago Store ID',
        help='Store ID for MercadoPago Point terminal'
    )
    mp_point_pos_id = fields.Char(
        string='MercadoPago POS ID',
        help='POS ID for MercadoPago Point terminal'
    )
