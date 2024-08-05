from odoo import models, api, fields, _


class AccountPaymentRegister(models.TransientModel):
    """
        Si bien cashbox depende de account_payment_pro y deshabilitamos los wizards de pago
        Modulos como hr_expenses continuan utilizando el wizard. por eso agregamos la logica de
        las seciones de caja tambien al wizard
    """

    _inherit = 'account.payment.register'

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
    @api.depends('journal_id')
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

    @api.depends('payment_type', 'cashbox_session_id')
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for pay in self.filtered('cashbox_session_id'):
            # hacemos dominio sobre los line_ids y no los diarios del pop config porque
            # puede ser que sea una sesion vieja y que el setting pop config cambie
            pay.available_journal_ids = pay.available_journal_ids._origin.filtered(
                lambda x: x in pay.cashbox_session_id.line_ids.mapped('journal_id'))
