##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    allowed_cashbox_ids = fields.Many2many(
        "account.cashbox",
        relation="account_cashbox_users_rel",
        column1="user_id",
        column2="cashbox_id",
    )
    requiere_account_cashbox_session = fields.Boolean()

    default_cashbox_id = fields.Many2one(
        comodel_name="account.cashbox",
        domain="[('id', 'in', allowed_cashbox_ids)]",
        help="""In the case of concurrent sessions in the selected cashbox,
        the most recently created session for that cashbox will be assigned to the payments.""",
    )

    @api.onchange("allowed_cashbox_ids")
    def _onchange_allowed_cashbox_ids(self):
        if self.default_cashbox_id.id not in self.allowed_cashbox_ids.ids:
            self.default_cashbox_id = False
