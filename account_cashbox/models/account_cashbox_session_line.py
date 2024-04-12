##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class PopSessionJournalControl(models.Model):

    _name = 'account.cashbox.session.line'
    _description = 'session journal'

    cashbox_session_id = fields.Many2one('account.cashbox.session', string='Session', required=True, ondelete='cascade')
    journal_id = fields.Many2one('account.journal', required=True, ondelete='cascade')
    # a balance_start por ahora lo estamos almacenando y no lo hacemos computado directamente cosa de que si cambia
    # algo en el orden o en el medio no se recompute todo. Balance end por ahora si lo computamos on the fly porque de
    # ultima los cambios afectarian solo esta session.
    # Luego tal vez veremos de trackear y/o guardar lo efectivamente contado
    balance_start = fields.Monetary(currency_field='currency_id')
    balance_end_real = fields.Monetary('Real Ending Balance', currency_field='currency_id')
    balance_end = fields.Monetary('Ending Balance', currency_field='currency_id', compute='_compute_amounts')
    amount = fields.Monetary('Amount',  currency_field='currency_id', compute='_compute_amounts')
    currency_id = fields.Many2one('res.currency', compute="_compute_curency")
    require_cash_control = fields.Boolean('require_cash_control', compute='_compute_require_cash_control')

    _sql_constraints = [('uniq_line', 'unique(cashbox_session_id, journal_id)', "Control line must be unique")]

    # @api.depends('cashbox_session_id.payment_ids.state', 'balance_start')
    # def _compute_amounts_old(self):
    #     # agrupamos por session porque lo mas usual es ver todos los registors de una misma session
    #     for session in self.mapped('cashbox_session_id'):
    #         session_recs = self.filtered(lambda x: x.cashbox_session_id == session)
    #         balance_lines = self.env['account.payment']._read_group([
    #             ('cashbox_session_id', '=', session.id), ('state', '=', 'posted'),
    #             ('journal_id', 'in', session_recs.mapped('journal_id').ids)],
    #             ['amount','payment_type'], ['journal_id','payment_type'], lazy=False)
    #         session_recs.write({'amount':0})
    #         for balance_line in balance_lines:
    #             with_balance = session_recs.filtered(lambda x: x.journal_id.id == balance_line['journal_id'][0])
    #             with_balance.amount += -balance_line['amount'] if balance_line['payment_type'] == 'outbound' else balance_line['amount']
    #         for with_balance in session_recs:
    #             with_balance.balance_end = with_balance.amount + with_balance.balance_start
    #             self -= with_balance
    #     self.amount = False
    #     self.balance_end = False

    @api.depends('cashbox_session_id.payment_ids','cashbox_session_id.payment_ids.state', 'balance_start')
    def _compute_amounts(self):
        payments_lines = self.env['account.payment'].search([
                ('cashbox_session_id', 'in', self.mapped('cashbox_session_id').ids), ('state', '=', 'posted')])
        for record in self:
            amount = sum(payments_lines.filtered(
                lambda p: p.cashbox_session_id == record.cashbox_session_id and p.journal_id == record.journal_id
                ).mapped('amount_signed'))
            record.amount = amount
            record.balance_end = amount + record.balance_start
            self -= record
        self.amount = False
        self.balance_end = False

    @api.depends('cashbox_session_id.cashbox_id.cash_control_journal_ids', 'journal_id')
    def _compute_require_cash_control(self):
        for rec in self:
            rec.require_cash_control = rec.journal_id.id in rec.cashbox_session_id.cashbox_id.cash_control_journal_ids.ids

    @api.depends('journal_id')
    def _compute_curency(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.journal_id.company_id.currency_id

    def action_session_payments(self):
        return self.with_context(search_default_journal_id=self.journal_id.id).cashbox_session_id.action_session_payments()
