##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class PopConfig(models.Model):

    _name = 'pop.config'
    _description = 'Point of Payment config'

    name = fields.Char(
        required=True,
    )
    code = fields.Char(
        'code',
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.user.company_id
    )
    journal_ids = fields.Many2many(
        'account.journal', 'pop_journal_rel',
        'pop_id', 'journal_id', string='Payment method',
        domain=[('type', 'in', ['bank', 'cash'])],
        check_company=True
    )
    allowed_res_users_ids = fields.Many2many(
        'res.users',
        relation= 'pos_config_users_rel',
        column1= 'config_id',
        column2= 'user_id',
    )

    cash_control_journal_ids = fields.Many2many('account.journal', string='cash control journal')
    session_ids = fields.One2many('pop.session', 'pop_id', string='Sessions')
    current_session_id = fields.Many2one('pop.session', compute='_compute_current_session', string="Current Session")
    current_session_state = fields.Char(compute='_compute_current_session')
    pop_session_username = fields.Char(compute='_compute_current_session_user')
    pop_session_state = fields.Char(compute='_compute_current_session_user')
    pop_session_duration = fields.Char(compute='_compute_current_session_user')
    sequence_id = fields.Many2one('ir.sequence', string='Session sequence',
        help="Numbering of cash sessions.", copy=False)
    allow_concurrent_sessions = fields.Boolean('allow concurrent sessions')
    max_diff = fields.Float('Payment max diff')
    current_concurrent_session_ids = fields.Many2many('pop.session', compute='_compute_current_session', string="Current Sessions")

    _sql_constraints = [('uniq_name', 'unique(code, company_id)', "Code is unic by company")]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            allow_concurrent_sessions  = vals.get('allow_concurrent_sessions', True)
            if 'sequence_id' not in vals and not allow_concurrent_sessions:
                vals['sequence_id'] = self.env['ir.sequence'].sudo().create([{
                            'name': 'session %s' % vals['code'],
                            'padding': 6,
                            'prefix': "%s-" % vals['code'],
                            'code': "session_%s" % vals['code'],
                        }]).id
        return super().create(vals_list)



    def _compute_current_session_user(self):
        for pop in self:
            session = pop.session_ids.filtered(lambda s: s.state in ['opening_control', 'opened', 'closing_control'])
            if session:
                pop.pop_session_username = ', '.join(session[0].sudo().user_ids.mapped('display_name'))
                pop.pop_session_state = session[0].state
                pop.pop_session_duration = (
                    datetime.now() - session[0].start_at
                ).days if session[0].start_at else 0
            else:
                pop.pop_session_username = False
                pop.pop_session_state = False
                pop.pop_session_duration = 0

    @api.depends('session_ids')
    def _compute_current_session(self):
        for pop in self:
            session = pop.session_ids.filtered(lambda r: r.state != 'closed')
            # sessions ordered by id desc
            pop.current_session_id = session and session[0].id or False
            pop.current_concurrent_session_ids = session and session.ids or False
            pop.current_session_state = session and session[0].state or False

    def action_open_config(self):
        view = self.env.ref('point_of_payment.pop_config_view_form')
        return {
            'name': ('Config'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'pop.config',
            'res_id': self.id,
            'view_id': view.id,
            'type': 'ir.actions.act_window',
        }

    def action_open_session(self):
        """ new session button

        create one if none exist
        access cash control interface if enabled or start a session
        """
        self.ensure_one()
        if not self.current_session_id or self.allow_concurrent_sessions:
            self.current_session_id = self.env['pop.session'].create({
                'user_ids': [(4,self.env.uid)],
                'pop_id': self.id
            })
            return self._open_session(self.current_session_id.id)
        return self._open_session(self.current_session_id.id)

    def _open_session(self, session_id):
        view = self.env.ref('point_of_payment.view_pop_session_form')
        return {
            'name': ('Session'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'pop.session',
            'res_id': session_id,
            'view_id': False,
            'type': 'ir.actions.act_window',
        }

    @api.constrains('journal_ids')
    def _check_journal_ids(self):
        for record in self:
            if not record.journal_ids.filtered(lambda x: x.type == 'cash'):
                raise ValidationError("Debe informar un diario de tipo 'Efectivo' y con control de efectivo")
