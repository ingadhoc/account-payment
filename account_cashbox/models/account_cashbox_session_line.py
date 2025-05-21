##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import api, fields, models


class PopSessionJournalControl(models.Model):
    _name = "account.cashbox.session.line"
    _description = "session journal"

    cashbox_session_id = fields.Many2one("account.cashbox.session", string="Session", required=True, ondelete="cascade")
    journal_id = fields.Many2one("account.journal", required=True, ondelete="cascade")
    # a balance_start por ahora lo estamos almacenando y no lo hacemos computado directamente cosa de que si cambia
    # algo en el orden o en el medio no se recompute todo. Balance end por ahora si lo computamos on the fly porque de
    # ultima los cambios afectarian solo esta session.
    # Luego tal vez veremos de trackear y/o guardar lo efectivamente contado
    balance_start = fields.Monetary(currency_field="currency_id")
    balance_end_real = fields.Monetary("Real Ending Balance", currency_field="currency_id", default=0.0001)
    balance_end = fields.Monetary("Ending Balance", currency_field="currency_id", compute="_compute_amounts")
    balance_difference = fields.Monetary(
        "Difference",
        currency_field="currency_id",
        compute="_compute_balance_difference",
        help="The difference between the ending balance and the real ending balance",
        readonly=True,
    )

    amount = fields.Monetary(currency_field="currency_id", compute="_compute_amounts")
    currency_id = fields.Many2one("res.currency", compute="_compute_curency")
    require_cash_control = fields.Boolean("require_cash_control", compute="_compute_require_cash_control")

    _sql_constraints = [("uniq_line", "unique(cashbox_session_id, journal_id)", "Control line must be unique")]

    @api.depends("cashbox_session_id.payment_ids", "cashbox_session_id.payment_ids.state", "balance_start")
    def _compute_amounts(self):
        payments_lines = self.env["account.payment"].search(
            [("cashbox_session_id", "in", self.mapped("cashbox_session_id").ids), ("state", "!=", "draft")]
        )
        for record in self:
            amount = sum(
                payments_lines.filtered(
                    lambda p: p.cashbox_session_id == record.cashbox_session_id and p.journal_id == record.journal_id
                ).mapped("amount_signed")
            )
            record.amount = amount
            record.balance_end = amount + record.balance_start
            self -= record
        self.amount = False
        self.balance_end = False

    @api.depends("balance_end", "balance_end_real")
    def _compute_balance_difference(self):
        for rec in self:
            rec.balance_difference = rec.balance_end_real - rec.balance_end

    @api.depends("cashbox_session_id.cashbox_id.cash_control_journal_ids", "journal_id")
    def _compute_require_cash_control(self):
        for rec in self:
            rec.require_cash_control = (
                rec.journal_id.id in rec.cashbox_session_id.cashbox_id.cash_control_journal_ids.ids
            )

    @api.depends("journal_id")
    def _compute_curency(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.journal_id.company_id.currency_id

    def action_session_payments(self):
        return self.with_context(
            search_default_journal_id=self.journal_id.id
        ).cashbox_session_id.action_session_payments()
