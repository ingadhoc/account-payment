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

    @api.depends_context("uid")
    # dummy depends para que se compute(no estamos seguros porque solo con el depends_context no computa)
    @api.depends("partner_id")
    def _compute_requiere_account_cashbox_session(self):
        self.requiere_account_cashbox_session = self.env.user.requiere_account_cashbox_session

    def _compute_cashbox_session_id(self):
        for rec in self:
            session_ids = self.env["account.cashbox.session"].search(
                [
                    ("state", "=", "opened"),
                    "|",
                    ("user_ids", "=", self.env.uid),
                    ("user_ids", "=", False),
                ]
            )
            if len(session_ids) == 1:
                rec.cashbox_session_id = session_ids.id
            elif len(session_ids) > 1:
                rec.cashbox_session_id = self.env.user.default_cashbox_id.current_session_id
            else:
                rec.cashbox_session_id = False

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
                raise UserError(
                    _(
                        """Your user is required to use a payment session for each payment,
                        but no default cashbox is assigned or no session is open for the user."""
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
