from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    double_validation = fields.Boolean(
        'Double Validation on Payments?',
        help='Use two steps validation on payments to suppliers'
    )
