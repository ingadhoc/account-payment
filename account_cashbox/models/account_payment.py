##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    cashbox_session_id = fields.Many2one(
        "account.cashbox.session",
        string="POP Session",
        compute="_compute_cashbox_session_id",
        readonly=True,
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

    destination_cashbox_session_id = fields.Many2one(
        "account.cashbox.session",
        string="Destination POP Session",
        help="In case of internal transfer payments, this field indicates the destination POP session.",
        domain="[('state', '=', 'opened'), ('cashbox_id.journal_ids', '=', destination_journal_id), '|', ('user_ids', '=', uid), ('user_ids', '=', False)]",
    )

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_id(self):
        """Clear destination_cashbox_session_id when destination journal changes
        and no open sessions exist for the new journal"""
        if self.destination_journal_id:
            # Check if the current session is still valid for the new journal
            if self.destination_cashbox_session_id:
                valid_session = self.env["account.cashbox.session"].search_count(
                    [
                        ("id", "=", self.destination_cashbox_session_id.id),
                        ("state", "=", "opened"),
                        ("cashbox_id.journal_ids", "=", self.destination_journal_id.id),
                    ]
                )
                if not valid_session:
                    self.destination_cashbox_session_id = False
        else:
            self.destination_cashbox_session_id = False

    @api.depends("journal_id")
    def _compute_company_id(self):
        # journal_id puede pertenecer a la empresa padre (shared_to_branches=True) y el usuario
        # de sucursal no tiene acceso de lectura a ese res.company (res_company_rule_employee).
        # Usamos sudo() para evaluar la jerarquía sin disparar AccessError.
        for payment in self:
            if payment.journal_id.sudo().company_id not in payment.company_id.sudo().parent_ids:
                payment.company_id = (payment.journal_id.sudo().company_id or self.env.company)._accessible_branches()[
                    :1
                ]

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

    # sin @api.depends a propósito: el valor se fija al crear (o por contexto, ver
    # _create_paired_internal_transfer_payment) y se recalcula al registrar (action_post).
    # Con depends, el pago pareado de una transferencia interna —que debe quedar sin sesión—
    # recibiría una, y el pago creado por el wizard pisaría la que el usuario eligió ahí.
    def _compute_cashbox_session_id(self):
        for rec in self:
            session_ids = rec.available_cashbox_session_ids
            if len(session_ids) == 1:
                rec.cashbox_session_id = session_ids.id
            elif len(session_ids) > 1:
                # la caja por defecto del usuario sirve solo si su sesión está entre las operables
                default_session = self.env.user.default_cashbox_id.current_session_id
                rec.cashbox_session_id = default_session if default_session in session_ids else False
            else:
                rec.cashbox_session_id = False

    @api.model
    def default_get(self, fields_list):
        # sembramos cashbox_session_id con la sesion abierta de la caja por defecto del
        # usuario para que, en un pago nuevo, el diario se resuelva a partir de ella (via
        # _onchange_cashbox_session, mas abajo) en vez de al reves. Solo si journal_id
        # tambien esta en fields_list: eso significa que el caller no lo fijo explicito en
        # su propio create()/vals (default_get solo pide los campos ausentes de vals) - si
        # ya viene fijado (wizard de registro, transferencia masiva, un create() directo),
        # no hay que pisarlo con la caja por defecto a ciegas.
        defaults = super().default_get(fields_list)
        if (
            "cashbox_session_id" in fields_list
            and "journal_id" in fields_list
            and not defaults.get("cashbox_session_id")
        ):
            user = self.env.user
            if user.requiere_account_cashbox_session and user.default_cashbox_id:
                session = user.default_cashbox_id.current_session_id
                # la caja por defecto del usuario puede ser de otra compañía que la del pago
                # nuevo (multi-compañía sin jerarquía entre ellas, no solo sucursales): sin este
                # chequeo se sembraba una sesión ajena que ningún compute posterior corrige, ya
                # que journal_id se resuelve por su cuenta en la compañía actual.
                Session = self.env["account.cashbox.session"]
                available = Session.search(Session._get_available_domain(self.env.company))
                if session in available:
                    defaults["cashbox_session_id"] = session.id
        return defaults

    @api.constrains("journal_id", "currency_id", "cashbox_session_id")
    def check_journal_currency(self):
        for payment in self.filtered("cashbox_session_id"):
            if payment.journal_id.currency_id and payment.currency_id != payment.journal_id.currency_id:
                raise ValidationError(_("The currency of the journal must be the of the payment."))

    def _create_paired_internal_transfer_payment(self):
        for payment in self:
            super(
                AccountPayment,
                payment.with_context(
                    paired_transfer=True,
                    default_cashbox_session_id=payment.destination_cashbox_session_id,
                ),
            )._create_paired_internal_transfer_payment()
            if payment.paired_internal_transfer_payment_id:
                payment.paired_internal_transfer_payment_id.destination_cashbox_session_id = False

    def action_post(self):
        for rec in self.filtered(lambda x: x.state == "draft"):
            if not rec.cashbox_session_id and rec.requiere_account_cashbox_session:
                rec._compute_cashbox_session_id()
            elif rec.cashbox_session_id and rec.cashbox_session_id.state != "opened":
                raise UserError(
                    _(
                        "A payment (id %s) can't be posted on a pos session that is not open (session %s)",
                        rec.id,
                        rec.cashbox_session_id.name,
                    )
                )

            if (
                not self.env.context.get("paired_transfer")
                and rec.requiere_account_cashbox_session
                and not rec.cashbox_session_id
            ):
                # distinguimos la causa (diario sin ninguna caja vs. diario con caja pero sin
                # sesion abierta) recien en el mensaje: la bandera de arriba es un espejo puro
                # de la configuracion del usuario, no depende del diario.
                journal_in_cashbox_scope = (
                    self.env["account.cashbox"]
                    .sudo()
                    .search_count(
                        [("company_id", "parent_of", rec.company_id.id), ("journal_ids", "=", rec.journal_id.id)]
                    )
                )
                if not journal_in_cashbox_scope:
                    raise UserError(
                        _(
                            "Your user is required to use a payment session for each payment, but the payment "
                            "journal (%s) is not managed by any cashbox for this company.",
                            rec.journal_id.name,
                        )
                    )
                raise UserError(
                    _(
                        "Your user is required to use a payment session for each payment, but there is no open "
                        "session for the payment journal and company (or the default cashbox does not manage them)."
                    )
                )

        super().action_post()

    def action_cancel(self):
        closed_sessions = self.filtered(lambda x: x.cashbox_session_id.state == "closed")
        if closed_sessions:
            raise UserError(
                _("Can't cancel a payment on a closed payment session. Payment ids: %s") % closed_sessions.ids
            )
        super().action_cancel()

    @api.depends("payment_type", "cashbox_session_id")
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for pay in self.filtered("cashbox_session_id"):
            # hacemos dominio sobre los line_ids y no los diarios del pop config porque
            # puede ser que sea una sesion vieja y que el setting pop config cambie
            pay.available_journal_ids = pay.available_journal_ids._origin.filtered(
                lambda x: x in pay.cashbox_session_id.line_ids.mapped("journal_id")
            )

    @api.onchange("cashbox_session_id")
    def _onchange_cashbox_session(self):
        """Esto es para refrescar el primer journal seleccionado por si no esta en la lista de los permitidos.
        Me suena que en algun otro lugar lo hicimos de otra manera"""
        for rec in self:
            if rec.journal_id not in rec.available_journal_ids._origin:
                rec.journal_id = rec.available_journal_ids._origin[:1]
