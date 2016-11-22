# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    double_validation = fields.Boolean(
        'Double Validation on Payments?',
        help='Use two steps validation on payments to suppliers'
        # readonly=True,
    )
