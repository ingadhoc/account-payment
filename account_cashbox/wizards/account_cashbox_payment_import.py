##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _


class AccountCashboxPaymentImport(models.TransientModel):
    _name = 'account.cashbox.payment.import'
    _description = 'Import Payment into session'

    cashbox_session_id = fields.Many2one('account.cashbox.session', required=True, readonly=True, ondelete='cascade')
    available_journal_ids = fields.Many2many('account.journal', compute='_compute_available_journal_ids')
    payment_ids = fields.Many2many('account.payment', string='Payments')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'cashbox_session_id' in fields:
            pop_session = self.env['account.cashbox.session'].browse(self.env.context['active_id']) \
                if self.env.context.get('active_model') == 'account.cashbox.session' else self.env['account.cashbox.session']
            res['cashbox_session_id'] = pop_session.id
        return res

    @api.depends('cashbox_session_id')
    def _compute_available_journal_ids(self):
        for rec in self:
            rec.available_journal_ids = rec.cashbox_session_id.line_ids.mapped('journal_id')

    def action_import_payment(self):
        self.payment_ids.cashbox_session_id = self.cashbox_session_id
        payment_journals = self.payment_ids.mapped('journal_id.display_name')
        self.cashbox_session_id.message_post(body='Import payments in journals %s' % ', '.join(payment_journals))
