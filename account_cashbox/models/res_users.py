##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_pop_config_ids = fields.Many2many(
        'pop.config',
        relation='pop_config_users_rel',
        column1='user_id',
        column2='config_id',
    )
    requiere_pop_session = fields.Boolean()
