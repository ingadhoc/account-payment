from odoo import fields, models

from .res_partner import ADD_CHECK_CREDIT_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_latam_check_add_credit = fields.Boolean(
        string="Include Third Party Checks on Hand",
        config_parameter=ADD_CHECK_CREDIT_PARAM,
        help="Add the third party checks on hand to the partner's amount due when checking the credit limit. "
        "Applies to every company of the database.",
    )
