##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError

POP_SESSION_STATE = [
    ('draft', 'Draft'),
    ('opened', 'Opened'),
    ('closing_control', 'Close control'),
    ('closed', 'Published'),
]


class AccountCashboxSession(models.Model):
    _name = 'account.cashbox.session'
    _order = 'opening_date desc'
    _description = 'Cashbox session'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    cashbox_id = fields.Many2one('account.cashbox', required=True, readonly=True)
    name = fields.Char(required=True, compute='_compute_name', store=True, readonly=False)
    restrict_users = fields.Boolean(related="cashbox_id.restrict_users")
    user_ids = fields.Many2many(
        'res.users', required=True, readonly=False, tracking=True, compute='_compute_user_ids', store=True)
    opening_date = fields.Datetime(readonly=True, copy=False)
    closing_date = fields.Datetime(readonly=True, copy=False)
    state = fields.Selection(
        POP_SESSION_STATE, required=True, readonly=False, tracking=True,
        index=True, copy=False, default='draft')
    line_ids = fields.One2many(
        'account.cashbox.session.line', 'cashbox_session_id', compute='_compute_line_ids', store=True, readonly=False)
    payment_ids = fields.One2many('account.payment', 'cashbox_session_id')
    require_cash_control = fields.Boolean('require_cash_control', compute='_compute_require_cash_control')
    allow_dates_edition = fields.Boolean(related='cashbox_id.allow_dates_edition')
    allow_concurrent_sessions = fields.Boolean(related='cashbox_id.allow_concurrent_sessions')
    company_id = fields.Many2one(related='cashbox_id.company_id', store=True)

    _sql_constraints = [('uniq_name_cashbox', 'unique(name, cashbox_id)', "El nombre de esta sesión de caja debe ser único!")]

    @api.depends('cashbox_id')
    def _compute_user_ids(self):
        for rec in self:
            rec.user_ids = [(4, self.env.uid)] if rec.cashbox_id.restrict_users else False

    @api.depends('cashbox_id')
    def _compute_name(self):
        for rec in self:
            rec.name = False if rec.cashbox_id.allow_concurrent_sessions else '/'

    @api.depends('cashbox_id')
    def _compute_line_ids(self):
        for rec in self:
            balance_start = {}
            if not rec.allow_concurrent_sessions:
                # TODO se podria hacer un read group aunque balance_end por ahora no es stored
                for journal in rec.cashbox_id.cash_control_journal_ids:
                    leaf = [('cashbox_session_id.cashbox_id', '=', rec.cashbox_id.id),
                        ('journal_id', '=', journal.id), ('cashbox_session_id.state', '=', 'closed')]
                    last_session = rec.env['account.cashbox.session'].sudo().search([('cashbox_id', '=', rec.cashbox_id.id), ('state', '=', 'closed')], order="closing_date desc", limit=1)
                    if last_session:
                        leaf.append(('cashbox_session_id', '=', last_session.id))
                    balance_start[journal.id] = rec.env['account.cashbox.session.line'].sudo().search(leaf, limit=1).balance_end_real
            rec.line_ids = [Command.clear()] + [
                Command.create({
                    'journal_id': journal.id,
                    'balance_start': balance_start.get(journal.id),
                }) for journal in rec.cashbox_id.journal_ids]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            account_cashbox = self.env['account.cashbox'].browse(vals['cashbox_id'])
            if not account_cashbox.allow_concurrent_sessions:
                vals['name'] = account_cashbox.sequence_id.next_by_id()
        return super().create(vals_list)

    def action_import_payments(self):
        view_id = self.env.ref('account_cashbox.cashbox_payment_import_view_form').id
        view = {
            "name": _("Import payment"),
            "view_mode": "form",
            "view_id": view_id,
            "view_type": "form",
            "res_model": "account.cashbox.payment.import",
            "res_id": False,
            "type": "ir.actions.act_window",
            "target": "new",
            "context": {"default_cashbox_id": self.cashbox_id.id, 'default_cashbox_session_id': self.id},
        }
        return view

    @api.depends('cashbox_id.cash_control_journal_ids')
    def _compute_require_cash_control(self):
        for rec in self:
            rec.require_cash_control = bool(len(rec.cashbox_id.cash_control_journal_ids))

    def action_account_cashbox_session_reopen(self):
        self.state = 'draft'

    def action_account_cashbox_session_open(self):
        for session in self:
            values = {}
            if not session.opening_date:
                values['opening_date'] = fields.Datetime.now()
            values['state'] = 'opened'
            session.write(values)

    def action_closing_control(self):
        for session in self:
            values = {}
            if not session.closing_date:
                values['closing_date'] = fields.Datetime.now()
            values['state'] = 'closing_control'
            session.write(values)

    def action_account_cashbox_session_close(self):
        self.write({'state': 'closed'})

    @api.constrains('state')
    def _check_session_balance(self):
        for rec in self.filtered(lambda x: x.state == 'closed'):
            for line in rec.line_ids.filtered(lambda c: c.journal_id.id in rec.cashbox_id.cash_control_journal_ids.ids):
                # if amounts are the same do not check
                if rec.company_id.currency_id.compare_amounts(line.balance_end, line.balance_end_real) == 0:
                    continue
                max_diff_in_currency = line.cashbox_session_id.cashbox_id.max_diff
                if line.journal_id.currency_id:
                    max_diff_in_currency = line.journal_id.currency_id._convert(
                        line.cashbox_session_id.cashbox_id.max_diff, line.cashbox_session_id.cashbox_id.company_id.currency_id)

                diff = abs(line.balance_end - line.balance_end_real)
                if diff > max_diff_in_currency:
                    raise ValidationError(_(
                        'En el diario "%s" el Balance Final Real (%s) excede la máxima diferencia permitida (%s).' % (
                            line.journal_id.name,
                            line.balance_end_real,
                            max_diff_in_currency,
                        )))

    def action_session_payments(self):
        view = self.env.ref('account.view_account_payment_tree')
        return {
            'name': self.name,
            'view_type': 'tree',
            'view_mode': 'tree',
            'res_model': 'account.payment',
            'domain': [('cashbox_session_id', '=', self.id)],
            'view_id': view.id,
            'type': 'ir.actions.act_window',
            'context': {'search_default_state_posted':True},
        }

    @api.ondelete(at_uninstall=False)
    def _unlink_check_state(self):
        if any(x.state != 'draft' for x in self):
            raise UserError(_('You can only delete sessions in "OPEN CONTROL" status.'))

    @api.constrains('state', 'cashbox_id')
    def _check_active_cashbox(self):
        for rec in self.filtered(lambda x: x.state != 'closed' and not x.cashbox_id.allow_concurrent_sessions ):
            other_opened_sessions = self.search([('state', '!=', 'closed'), ('id', '!=', rec.id), ('cashbox_id', '=', rec.cashbox_id.id)])
            if other_opened_sessions:
                raise UserError(_('You can only have one open Session for %s' % rec.cashbox_id.display_name))
