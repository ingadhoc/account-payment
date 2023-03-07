##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _


class PopPaymentImport(models.TransientModel):
    _name = 'pop.payment.import'
    _description = 'Import Payment into session'

    pop_session_id = fields.Many2one('pop.session', required=True, readonly=True, ondelete='cascade')
    available_journal_ids = fields.Many2many('account.journal', compute='_compute_available_journal_ids')
    payment_ids = fields.Many2many('account.payment', string='Payments')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'pop_session_id' in fields:
            pop_session = self.env['pop.session'].browse(self.env.context['active_id']) \
                if self.env.context.get('active_model') == 'pop.session' else self.env['pop.session']
            res['pop_session_id'] = pop_session.id
        return res

    @api.depends('pop_session_id')
    def _compute_available_journal_ids(self):
        for rec in self:
            rec.available_journal_ids = rec.pop_session_id.journal_control_ids.mapped('journal_id')

    def action_import_payment(self):
        self.payment_ids.pop_session_id = self.pop_session_id
