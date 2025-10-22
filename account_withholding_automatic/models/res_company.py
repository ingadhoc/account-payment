##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class ResCompany(models.Model):

    _inherit = "res.company"

    automatic_withholdings = fields.Boolean(
        help="Make withholdings automatically on payments confirmation"
    )
