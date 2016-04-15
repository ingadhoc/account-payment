# -*- coding: utf-8 -*-
from openerp import models, fields


class res_company(models.Model):
    _inherit = "res.company"

    double_validation = fields.Boolean(
        'Double Validation?',
        help='Use two steps validation on payments to suppliers of this '
        'journal?',
        )
