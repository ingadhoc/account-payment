##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ResUsers(models.Model):
    _inherit = 'res.users'

    default_pop_id = fields.Many2one(
        'pop.config',
        string='Caja por defecto',
        help="Caja por defecto para el usuario.")

    selected_pop_id = fields.Many2one(
        'pop.config',
        string='Caja seleccionada',
        help="Caja con la que está actualmente operando el usuario.")

    def get_selected_pop_id(self):
        if self.selected_pop_id:
            return self.selected_pop_id
        else:
            raise UserError("Debe seleccionar una caja")
