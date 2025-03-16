##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_cashbox_ids = fields.Many2many(
        'account.cashbox',
        relation='account_cashbox_users_rel',
        column1='user_id',
        column2='cashbox_id',
    )
    requiere_account_cashbox_session = fields.Boolean()
