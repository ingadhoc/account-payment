# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _
from openerp.exceptions import ValidationError


class ResCompany(models.Model):

    _inherit = "res.company"

    automatic_withholdings = fields.Boolean(
        help='Make withholdings automatically on payments confirmation'
    )

    @api.multi
    @api.constrains('double_validation', 'automatic_withholdings')
    def check_double_validation(self):
        for rec in self:
            if rec.automatic_withholdings and not rec.double_validation:
                raise ValidationError(_(
                    'To use automatic withholdings double validation is '
                    'required'))
