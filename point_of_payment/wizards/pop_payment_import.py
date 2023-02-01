##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class PopPaymentImport(models.Model):
    _name = 'pop.payment.import'
    _description = 'Import Payment into session'

    pop_id = fields.Many2one(
        'pop.config', string='POP',
        help="Caja física que usará.",
        required=True,
    )
    pop_session_id = fields.Many2one(
        'pop.session',
        string='Session',
        required=True,
        #domain = [('pop_id', '=', pop_id)]
    )
    payment_ids = fields.Many2many('account.payment', string='Payments')

    @api.depends('pop_id')
    def set_session(self):
        for rec in self:
            rec.pop_session_id = rec.pop_id.session_ids[-1]

    def action_import_payment(self):
        update_payment_ids  = self.payment_ids.filtered(lambda p: p.pop_session_id is False and p.journal_id in p.journal_ids.ids)
        update_payment_ids.pop_session_id = self.pop_session_id.id