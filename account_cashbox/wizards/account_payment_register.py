from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    """
    Si bien cashbox depende de account_payment_pro y deshabilitamos los wizards de pago
    Modulos como hr_expenses continuan utilizando el wizard. por eso agregamos la logica de
    las seciones de caja tambien al wizard
    """

    _inherit = "account.payment.register"

    cashbox_session_id = fields.Many2one(
        "account.cashbox.session",
        string="POP Session",
        compute="_compute_cashbox_session_id",
        readonly=False,
        store=True,
    )
    requiere_account_cashbox_session = fields.Boolean(
        compute="_compute_requiere_account_cashbox_session",
        compute_sudo=False,
    )
    available_cashbox_session_ids = fields.Many2many(
        "account.cashbox.session",
        compute="_compute_available_cashbox_session_ids",
    )

    @api.depends_context("uid")
    def _compute_requiere_account_cashbox_session(self):
        for rec in self:
            rec.requiere_account_cashbox_session = self.env.user.requiere_account_cashbox_session

    @api.depends("company_id", "journal_id")
    def _compute_available_cashbox_session_ids(self):
        Session = self.env["account.cashbox.session"]
        for rec in self:
            rec.available_cashbox_session_ids = Session.search(
                Session._get_available_domain(rec.company_id, journal=rec.journal_id)
            )

    # a diferencia del pago, acá sí lleva depends: el wizard no tiene un action_post que
    # recalcule, y sin esto el compute puede correr antes de que journal_id tenga valor.
    @api.depends("available_cashbox_session_ids")
    def _compute_cashbox_session_id(self):
        for rec in self:
            session_ids = rec.available_cashbox_session_ids
            if len(session_ids) == 1:
                rec.cashbox_session_id = session_ids.id
            else:
                rec.cashbox_session_id = False

    @api.depends("payment_type", "cashbox_session_id")
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for pay in self.filtered("cashbox_session_id"):
            # hacemos dominio sobre los line_ids y no los diarios del pop config porque
            # puede ser que sea una sesion vieja y que el setting pop config cambie
            pay.available_journal_ids = pay.available_journal_ids._origin.filtered(
                lambda x: x in pay.cashbox_session_id.line_ids.mapped("journal_id")
            )

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.cashbox_session_id:
            payment_vals["cashbox_session_id"] = self.cashbox_session_id.id
        return payment_vals
