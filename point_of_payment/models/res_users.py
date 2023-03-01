##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_pos_config_ids = fields.Many2many(
        'pop.config',
        relation= 'pos_config_users_rel',
        column1= 'user_id',
        column2= 'config_id',
    )
    requiere_pos_session = fields.Boolean()