##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

POP_SESSION_STATE = [
    ('opening_control', 'CONTROL DE APERTURA'),  # method action_pop_session_open
    ('opened', 'EN PROCESO'),               # method action_pop_session_closing_control
    ('closing_control', 'CONTROL DE CIERRE'),  # method action_pop_session_close
    ('closed', 'CERRADO & PUBLICADO'),
]


class PopSession(models.Model):
    _name = 'pop.session'
    _order = 'id desc'
    _description = 'point of payment session'
    _inherit = ['mail.thread', 'mail.activity.mixin']


    pop_id = fields.Many2one(
        'pop.config', string='POP',
        help="Caja física que usará.",
        required=True,
    )
    name = fields.Char(string='ID de la sesión', required=True, default='/')
    user_ids = fields.Many2many(
        'res.users', string='Responsibles',
        required=True,
        readonly=True,
        states={'opening_control': [('readonly', False)]},
        default=lambda self: [(4,self.env.uid)])

    start_at = fields.Datetime(string='Opening date', readonly=True)
    stop_at = fields.Datetime(string='Close date', readonly=True, copy=False)
    state = fields.Selection(
        POP_SESSION_STATE, string='Status',
        required=True, readonly=True,
        index=True, copy=False, default='opening_control',
    )
    journal_ids = fields.Many2many(
        'account.journal',
        related='pop_id.journal_ids',
        readonly=True,
        string='Payment methods'
    )
    journal_control_ids = fields.One2many(
        'pop.session.journal_control',
        'pop_session_id',
        store=True,
        compute='_compute_control_lines',
        readonly=False,
        string='Journal control'
    )
    waiting_transfer_ids = fields.Many2many('account.payment', compute='_compute_waiting_transfer')
    count_waiting_transfer = fields.Integer()
    require_cash_control = fields.Boolean('require_cash_control', compute='_compute_require_cash_control')
    payment_ids = fields.One2many('account.payment', 'pop_session_id', string='payments')
    allow_concurrent_sessions = fields.Boolean('allow concurrent sessions', related='pop_id.allow_concurrent_sessions')
    cash_control_journal_ids = fields.Many2many('account.journal', compute='_compute_cash_control_journal_ids' , string='cash control journal')

    _sql_constraints = [('uniq_name', 'unique(name)', "El nombre de esta sesión de caja debe ser único !")]

    def action_import_payments(self):
        view_id = self.env.ref('point_of_payment.pop_payment_import_view_form').id

        view = {
            "name": _("Import payment"),
            "view_mode": "form",
            "view_id": view_id,
            "view_type": "form",
            "res_model": "pop.payment.import",
            "res_id": False,
            "type": "ir.actions.act_window",
            "target": "new",
            "context": {"default_pop_id": self.pop_id.id, 'default_pop_session_id': self.id},
        }
        return view


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            pop_config = self.env['pop.config'].browse(vals['pop_id'])
            if not pop_config.allow_concurrent_sessions :
                vals['name'] = pop_config.sequence_id.next_by_id()
            if pop_config.cash_control_journal_ids:
                if pop_config.session_ids:
                    vals['journal_control_ids'] = [Command.create({
                        'journal_id': line.journal_id.id,
                        'currency_id': line.currency_id.id,
                        'balance_start': line.balance_end,
                        }) for line in pop_config.session_ids[0].journal_control_ids.filtered(lambda j: j.journal_id.id in pop_config.cash_control_journal_ids.ids)]

                else:
                    vals['journal_control_ids'] = [Command.create({
                        'journal_id': journal_id.id,
                        'currency_id': journal_id.currency_id.id,
                        }) for journal_id in pop_config.cash_control_journal_ids]

        return super().create(vals_list)

    @api.depends('pop_id')
    def _compute_waiting_transfer(self):
        for rec in self:
            rec.waiting_transfer_ids = self.env['account.payment'].search([('dest_pop_id','=',rec.pop_id),('dest_pop_session_id','=', False)])

    @api.depends('pop_id')
    def _compute_cash_control_journal_ids(self):
        for rec in self:
            rec.cash_control_journal_ids = rec.pop_id.cash_control_journal_ids

    @api.depends('pop_id.cash_control_journal_ids')
    def _compute_require_cash_control(self):
        for rec in self:
            rec.require_cash_control = bool(len(rec.pop_id.cash_control_journal_ids))

    def action_pop_session_open(self):
        for session in self.filtered(lambda session: session.state == 'opening_control'):
            values = {}
            if not session.start_at:
                values['start_at'] = fields.Datetime.now()
            values['state'] = 'opened'
            session.write(values)
        return True

    def action_closing_control(self):
        for session in self:
            session.write({'state': 'closing_control', 'stop_at': fields.Datetime.now()})

    def action_box_session_back_to_opened(self):
        for session in self:
            session.write({'state': 'opened'})

    def _check_pop_session_balance(self):
        for rec in self:
            control_lines = self.mapped('journal_control_ids').filtered(lambda c: c.journal_id.id in rec.pop_id.cash_control_journal_ids.ids)
            control_lines._validate_diff()

    @api.depends('payment_ids', 'payment_ids.state')
    def _compute_control_lines(self):
        for rec in self:
            balance_lines = self.env['account.payment'].read_group(
                [('pop_session_id', '=', rec.id), ('state', '=', 'posted')],
                ['amount_total_signed'],['journal_id'],
                lazy=False
            )
            for line in balance_lines:
                control_line = rec.journal_control_ids.filtered(lambda c: c.journal_id.id == line['journal_id'][0])
                if control_line:
                    control_line.amount = line['amount_total_signed']
                else:
                    rec.journal_control_ids = [Command.create({
                        'journal_id': line['journal_id'][0],
                        'amount': line['amount_total_signed'],
                        })]

    def action_session_validate(self):
        self._check_pop_session_balance()
        return self.action_pop_session_close()

    def action_pop_session_close(self):
        self.write({'state': 'closed'})
        #return self.env.ref('point_of_payment.pop_config_action')


    def get_session_journal_id(self, journal_id):
        return self.pop_session_journal_ids.filtered(lambda x: x.journal_id.id == journal_id.id)

    def action_open_session(self):
        return {
            'name': ('Session'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'pop.session',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
        }

    def action_session_payments(self):
        view = self.env.ref('account.view_account_payment_tree')
        return {
            'name': self.name,
            'view_type': 'tree',
            'view_mode': 'tree',
            'res_model': 'account.payment',
            'domain':[('pop_session_id','=',self.id)],
            'view_id': view.id,
            'type': 'ir.actions.act_window',
        }


class PopSessionJournalControl(models.Model):

    _name = 'pop.session.journal_control'
    _description = 'session journal'

    pop_session_id = fields.Many2one('pop.session', string='Session')
    journal_id = fields.Many2one('account.journal', string='Journal')
    currency_id = fields.Many2one('res.currency', string='Currency', compute="_compute_curency")
    balance_start = fields.Monetary('Balance start',  currency_field='currency_id')
    amount = fields.Monetary('amount',  currency_field='currency_id')
    balance_end = fields.Monetary('Balance end',  currency_field='currency_id')
    diff = fields.Monetary('Diff',  currency_field='currency_id')
    require_cash_control = fields.Boolean('require_cash_control', compute='_compute_require_cash_control')

    @api.depends('pop_session_id.pop_id.cash_control_journal_ids', 'journal_id')
    def _compute_require_cash_control(self):
        for rec in self:
            rec.require_cash_control = rec.journal_id.id in rec.pop_session_id.pop_id.cash_control_journal_ids.ids

    @api.depends('journal_id')
    def  _compute_curency(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.journal_id.company_id.currency_id

    def action_session_payments(self):
        view = self.env.ref('account.view_account_payment_tree')
        return {
            'name': self.pop_session_id.name,
            'view_type': 'tree',
            'view_mode': 'tree',
            'res_model': 'account.payment',
            'domain':[('pop_session_id','=',self.pop_session_id.id), ('journal_id', '=', self.journal_id.id )],
            'view_id': view.id,
            'type': 'ir.actions.act_window',
        }

    def _validate_diff(self):
        for line in self:
            diff = 0
            if float_compare(line.balance_end, line.balance_start + line.amount, precision_rounding=line.currency_id.rounding) != 0:
                if line.pop_session_id.allow_concurrent_sessions:
                    diff = line.amount - line.balance_end
                else:
                    diff = line.balance_start + line.amount - line.balance_end
            max_diff_in_currency = line.pop_session_id.pop_id.max_diff
            if line.journal_id.currency_id:
                max_diff_in_currency = line.journal_id.currency_id(line.pop_session_id.pop_id.max_diff, line.pop_session_id.pop_id.company_id.currency_id)

            if  max_diff_in_currency > diff:
                raise ValidationError(
                    _('exceeded the maximum difference in journal %s.' % line.journal_id.display_name))
            # TODO: esto no se si lo queremos
            elif diff < 0:
                raise ValidationError(
                    _('Final balance cannot be negative in journal %s.' % line.journal_id.display_name))

            line.diff = diff


    _sql_constraints = [('uniq_line', 'unique(pop_session_id, journal_id)', "Control line must be unique")]

