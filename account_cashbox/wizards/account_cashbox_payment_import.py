##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _


class AccountCashboxPaymentImport(models.TransientModel):
    _name = 'account.cashbox.payment.import'
    _description = 'Import Payment into session'

    account_cashbox_session_id = fields.Many2one('account.cashbox.session', required=True, readonly=True, ondelete='cascade')
    available_journal_ids = fields.Many2many('account.journal', compute='_compute_available_journal_ids')
    payment_ids = fields.Many2many('account.payment', string='Payments')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'account_cashbox_session_id' in fields:
            pop_session = self.env['account.cashbox.session'].browse(self.env.context['active_id']) \
                if self.env.context.get('active_model') == 'account.cashbox.session' else self.env['account.cashbox.session']
            res['account_cashbox_session_id'] = pop_session.id
        return res

    @api.depends('account_cashbox_session_id')
    def _compute_available_journal_ids(self):
        for rec in self:
            rec.available_journal_ids = rec.account_cashbox_session_id.line_ids.mapped('journal_id')

    def action_import_payment(self):
        self.payment_ids.account_cashbox_session_id = self.account_cashbox_session_id
