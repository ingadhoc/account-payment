# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    double_validation = fields.Boolean(
        "Double Validation on Payments?",
        help="Use two steps validation on payments to suppliers",
    )
