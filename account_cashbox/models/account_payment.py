##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    cashbox_session_id = fields.Many2one(
        'account.cashbox.session',
        string='POP Session',
        compute="_compute_cashbox_session_id",
        readonly=True,
        store=True
    )
    requiere_account_cashbox_session = fields.Boolean(
        compute='_compute_requiere_account_cashbox_session',
        compute_sudo=False,
    )

    @api.depends_context('uid')
    # dummy depends para que se compute(no estamos seguros porque solo con el depends_context no computa)
    @api.depends('partner_id')
    def _compute_requiere_account_cashbox_session(self):
        self.requiere_account_cashbox_session = self.env.user.requiere_account_cashbox_session

    def _compute_cashbox_session_id(self):
        for rec in self:
            session_ids = self.env['account.cashbox.session'].search([
                ('state', '=', 'opened'),
                '|',
                ('user_ids', '=', self.env.uid),
                ('user_ids', '=', False),
            ])
            if len(session_ids) == 1:
                rec.cashbox_session_id = session_ids.id
            else:
                rec.cashbox_session_id = False

    @api.constrains('journal_id', 'currency_id', 'cashbox_session_id')
    def check_journal_currency(self):
        for payment in self.filtered('cashbox_session_id'):
            if payment.journal_id.currency_id and payment.currency_id != payment.journal_id.currency_id:
                raise ValidationError(
                    _('The currency of the journal must be the of the payment.'))

    def _create_paired_internal_transfer_payment(self):
        super(AccountPayment, self.with_context(paired_transfer=True))._create_paired_internal_transfer_payment()

    def action_post(self):
        for rec in self:
            if rec.cashbox_session_id and rec.cashbox_session_id.state != 'opened':
                raise UserError(_(
                    "A payment (id %s) can't be posted on a pos session that is not open (session %s)'" % (
                        rec.id, rec.cashbox_session_id.name
                    )))

            if  not self.env.context.get('paired_transfer') and self.env.user.requiere_account_cashbox_session and not rec.cashbox_session_id:
                raise UserError(_('Your user requires to use payment session on each payment'))

        super().action_post()

    def action_cancel(self):
        closed_sessions = self.filtered(lambda x: x.cashbox_session_id.state == 'closed')
        if closed_sessions:
            raise UserError(_(
                "Can't cancel a payment on a closed payment session. Payment ids: %s") % closed_sessions.ids)
        super().action_cancel()

    @api.depends('payment_type', 'cashbox_session_id')
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for pay in self.filtered('cashbox_session_id'):
            # hacemos dominio sobre los line_ids y no los diarios del pop config porque
            # puede ser que sea una sesion vieja y que el setting pop config cambie
            pay.available_journal_ids = pay.available_journal_ids._origin.filtered(
                lambda x: x in pay.cashbox_session_id.line_ids.mapped('journal_id'))

    @api.onchange('cashbox_session_id')
    def _onchange_cashbox_session(self):
        """ Esto es para refrescar el primer journal seleccionado por si no esta en la lista de los permitidos.
        Me suena que en algun otro lugar lo hicimos de otra manera"""
        for rec in self:
            if rec.journal_id not in rec.available_journal_ids._origin:
                rec.journal_id = rec.available_journal_ids._origin[:1]
