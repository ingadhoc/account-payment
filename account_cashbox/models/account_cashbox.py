##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountCashbox(models.Model):

    _name = 'account.cashbox'
    _description = 'Cashbox'
    _check_company_auto = True

    name = fields.Char(required=True,)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.user.company_id)
    journal_ids = fields.Many2many(
        'account.journal', 'cashbox_journal_rel', 'cashbox_id', 'journal_id', required=True,
        string='Payment method', domain=[('type', 'in', ['bank', 'cash'])], check_company=True)
    allowed_res_users_ids = fields.Many2many(
        'res.users', relation='account_cashbox_users_rel', column1='cashbox_id', column2='user_id',)
    cash_control_journal_ids = fields.Many2many('account.journal', string='Journals with Open / Close control')
    session_ids = fields.One2many('account.cashbox.session', 'cashbox_id')
    sequence_id = fields.Many2one('ir.sequence', help="Numbering of cash sessions.", copy=False,check_company=True,)
    allow_concurrent_sessions = fields.Boolean()
    max_diff = fields.Float(help='Max allowed difference for Cash Control Journals on the currency of the company')
    current_session_id = fields.Many2one('account.cashbox.session', compute='_compute_current_session', string="Current Session")
    current_concurrent_session_ids = fields.Many2many('account.cashbox.session', compute='_compute_current_session', string="Current Sessions")

    @api.depends('session_ids.state')
    def _compute_current_session(self):
        for cashbox in self:
            session = cashbox.session_ids.filtered(lambda r: r.state != 'closed')
            # sessions ordered by id desc
            cashbox.current_session_id = session and session[0].id or False
            cashbox.current_concurrent_session_ids = session and session.ids or False

    def action_open_cashbox(self):
        self.ensure_one()
        action = {
            'name': ('Cashbox'),
            'view_mode': 'form,tree',
            'res_model': 'account.cashbox',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
        }
        return action

    def action_open_session(self):
        self.ensure_one()
        action = {
            'name': ('Session'),
            'view_mode': 'form,tree',
            'res_model': 'account.cashbox.session',
            'res_id': self.current_session_id.id,
            'type': 'ir.actions.act_window',
            'context': {'default_cashbox_id': self.id, 'hide_cashbox_id': True}
        }
        return action

    @api.ondelete(at_uninstall=False)
    def _unlink_check_sessions(self):
        if any(x.session_ids for x in self):
            raise UserError(_('You cannot delete Point of Payments with sessions.'))
