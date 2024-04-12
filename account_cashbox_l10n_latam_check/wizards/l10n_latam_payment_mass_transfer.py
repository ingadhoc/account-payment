
from odoo import models, api, fields, _
from odoo.exceptions import UserError


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = 'l10n_latam.payment.mass.transfer'

    cashbox_session_id = fields.Many2one(
        'account.cashbox.session',
        string='POP Session',
        compute="_compute_cashbox_session_id",
        readonly=False,
        store=True
    )
    requiere_account_cashbox_session = fields.Boolean(
        compute='_compute_requiere_account_cashbox_session',
        compute_sudo=False,
    )

    @api.depends_context('uid')
    # dummy depends para que se compute(no estamos seguros porque solo con el depends_context no computa)
    @api.depends('destination_journal_id')
    def _compute_requiere_account_cashbox_session(self):
        self.requiere_account_cashbox_session = self.env.user.requiere_account_cashbox_session

    def _compute_cashbox_session_id(self):
        for rec in self:
            session_ids = self.env['account.cashbox.session'].search([
                ('state', '=', 'opened'),
                '|',
                ('user_ids', '=', self.env.uid),
                ('user_ids', '=', False)
            ])
            if len(session_ids) == 1:
                rec.cashbox_session_id = session_ids.id
            else:
                rec.cashbox_session_id = False

    def _create_payments(self):
        self.ensure_one()
        if self.env.user.requiere_account_cashbox_session and not self.cashbox_session_id:
            raise UserError(_('Your user requires to use payment session on each tranfer'))
        # Envio el contexto  paired_transfer en True para poder crear la
        # transferencia son cashbox durante la creacion y setearla sobre
        # la primera y no la paires
        payments = super(L10nLatamPaymentMassTransfer, self.with_context(paired_transfer=True))._create_payments()
        payments.cashbox_session_id = self.cashbox_session_id.id
        return payments
