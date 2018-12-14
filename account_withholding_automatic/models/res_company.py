##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):

    _inherit = "res.company"

    automatic_withholdings = fields.Boolean(
        help='Make withholdings automatically on payments confirmation'
    )
