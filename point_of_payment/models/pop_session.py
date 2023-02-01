##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
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
    _description = 'Sesiones de caja'
    _inherit = ['mail.thread', 'mail.activity.mixin']


    pop_id = fields.Many2one(
        'pop.config', string='POP',
        help="Caja física que usará.",
        required=True,
    )
    name = fields.Char(string='ID de la sesión', required=True, readonly=True, default='/')
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
        inverse='_inverse_control_lines',
        string='Journal control'
    )

    require_cash_control = fields.Boolean('require_cash_control', compute='_compute_require_cash_control')
    payment_ids = fields.One2many('account.payment', 'pop_session_id', string='payments')

    _sql_constraints = [('uniq_name', 'unique(name)', "El nombre de esta sesión de caja debe ser único !")]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            pop_config = self.env['pop.config'].browse(vals['pop_id'])
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
            #if session.cash_register_balance_end < 0:
            #    raise UserError(_("El saldo final no puede ser negativo."))
            session.write({'state': 'closing_control', 'stop_at': fields.Datetime.now()})

    def action_box_session_back_to_opened(self):
        for session in self:
            session.write({'state': 'opened'})

    def _check_pop_session_balance(self):
        for rec in self:
            for line in self.mapped('journal_control_ids').filtered(lambda c: c.journal_id.id in rec.pop_id.cash_control_journal_ids.ids):
                # TODO: que hacemos con las diferencias??
                if float_compare(line.balance_end, line.balance_start + line.amount, precision_rounding=line.currency_id.rounding) != 0:
                    line.diff = line.balance_start + line.amount - line.balance_end

    @api.depends('payment_ids', 'payment_ids.state')
    def _compute_control_lines(self):
        for rec in self:
            balance_lines = self.env['account.payment'].read_group(
                [('pop_session_id', '=', rec.id), ('state', '=', 'posted')],
                ['amount','amount_total_signed', 'currency_id'],['journal_id','currency_id'],
                lazy=False
            )
            for line in balance_lines:
                control_line = rec.journal_control_ids.filtered(lambda c: c.journal_id.id == line['journal_id'][0] and c.currency_id.id == line['currency_id'][0])
                if control_line:
                    control_line.amount = line['amount_total_signed']
                else:
                    rec.journal_control_ids = [Command.create({
                        'journal_id': line['journal_id'][0],
                        'currency_id': line['currency_id'][0],
                        'amount': line['amount_total_signed'],
                        })]

    def _inverse_control_lines(self):
        # dummie inverse
        pass

    def action_session_validate(self):
        self._check_pop_session_balance()
        return self.action_pop_session_close()

    def action_pop_session_close(self):
        self.write({'state': 'closed'})
        #return self.env.ref('point_of_payment.pop_config_action')


    def get_session_journal_id(self, journal_id):
        return self.pop_session_journal_ids.filtered(lambda x: x.journal_id.id == journal_id.id)


class PopSessionJournalControl(models.Model):

    _name = 'pop.session.journal_control'
    _description = 'session journal'

    pop_session_id = fields.Many2one('pop.session', string='Session')
    journal_id = fields.Many2one('account.journal', string='Journal')
    currency_id = fields.Many2one('res.currency', string='Currency')
    balance_start = fields.Monetary('Balance start',  currency_field='currency_id')
    amount = fields.Monetary('amount',  currency_field='currency_id')
    balance_end = fields.Monetary('Balance end',  currency_field='currency_id')
    diff = fields.Monetary('Diff',  currency_field='currency_id')

    _sql_constraints = [('uniq_line', 'unique(pop_session_id, journal_id, currency_id)', "Control line must be unique")]

