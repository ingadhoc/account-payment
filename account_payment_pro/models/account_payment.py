from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # Modelo tri-monetario: A (currency_id), B1 (counterpart_currency_id), B2 (destination_currency_id), C (company_currency_id)
    # desde account_payment_group, modelo account.payment
    counterpart_currency_amount = fields.Monetary(
        currency_field="counterpart_currency_id",
        compute="_compute_counterpart_currency_amount",
        inverse="_inverse_counterpart_currency_amount",
        store=True,
        readonly=False,
        copy=False,
    )
    counterpart_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_counterpart_currency_id",
        store=True,
        readonly=False,
    )
    destination_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_destination_currency_id",
        store=False,
    )
    counterpart_rate = fields.Float(
        readonly=False,
        compute="_compute_counterpart_rate",
        inverse="_inverse_counterpart_rate",
        store=True,
        copy=False,
        digits=0,
        min_display_digits=2,
    )
    accounting_rate = fields.Float(
        compute="_compute_accounting_rate",
        store=True,
        readonly=False,
        precompute=True,
        copy=False,
        digits=0,
        min_display_digits=2,
        help="Exchange rate A\u2192C in Odoo native format (e.g., 0.000667 for ARS/USD)",
    )
    user_accounting_rate = fields.Float(
        compute="_compute_user_accounting_rate",
        inverse="_inverse_user_accounting_rate",
        digits=0,
        min_display_digits=2,
    )
    user_counterpart_rate = fields.Float(
        compute="_compute_user_counterpart_rate",
        inverse="_inverse_user_counterpart_rate",
        digits=0,
        min_display_digits=2,
    )
    counterpart_currency_editable = fields.Boolean(
        compute="_compute_counterpart_currency_editable",
        help="True when the destination account does not force a specific currency, "
        "allowing the user to choose counterpart_currency_id from the form view.",
    )
    counterpart_rate_inverted = fields.Boolean(
        compute="_compute_counterpart_rate_inverted",
        help="True si el rate teórico A→B1 < 1.0 (B1 es la moneda fuerte). "
        "Determina la dirección de visualización de user_counterpart_rate.",
    )
    accounting_rate_inverted = fields.Boolean(
        compute="_compute_accounting_rate_inverted",
        help="True si el rate teórico A→C < 1.0 (C es la moneda fuerte). "
        "Determina la dirección de visualización de user_accounting_rate.",
    )
    # Campo técnico para round-trip del onchange: el cliente lo devuelve en cada llamada,
    # evitando depender de _origin (que no se actualiza entre onchanges y no existe en registros nuevos).
    previous_currency_id = fields.Many2one(
        "res.currency",
        store=True,
        copy=False,
    )
    amount_exact = fields.Float(
        string="Amount (Exact)",
        digits=0,
        copy=False,
        help="Exact value of amount with full precision, used internally for conversions to avoid rounding errors.",
    )
    journal_currency_id = fields.Many2one(related="journal_id.currency_id", string="Journal Currency")
    destination_journal_currency_id = fields.Many2one(
        related="destination_journal_id.currency_id",
        string="Destination Journal Currency",
    )
    commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    # MUY IMPORTANTE; NO agregar tracking porque rompe como se calcula (ver commit)
    payment_total = fields.Monetary(
        compute="_compute_payment_total",
        currency_field="destination_currency_id",
    )
    available_journal_ids = fields.Many2many(comodel_name="account.journal", compute="_compute_available_journal_ids")
    # desde account_payment_group, modelo account.payment.group
    matched_amount = fields.Monetary(
        compute="_compute_matched_amounts",
        currency_field="destination_currency_id",
    )
    unmatched_amount = fields.Monetary(
        compute="_compute_matched_amounts",
        currency_field="destination_currency_id",
    )
    selected_debt = fields.Monetary(
        compute="_compute_selected_debt",
        currency_field="destination_currency_id",
    )
    unreconciled_amount = fields.Monetary(
        string="Adjustment / Advance",
        currency_field="destination_currency_id",
    )
    # reconciled_amount = fields.Monetary(compute='_compute_amounts')
    to_pay_amount = fields.Monetary(
        compute="_compute_to_pay_amount",
        inverse="_inverse_to_pay_amount",
        readonly=True,
        tracking=True,
        currency_field="destination_currency_id",
    )
    has_outstanding = fields.Boolean(
        compute="_compute_has_outstanding",
    )
    to_pay_move_line_ids = fields.Many2many(
        "account.move.line",
        "account_move_line_payment_to_pay_rel",
        "payment_id",
        "to_pay_line_id",
        string="To Pay Lines",
        compute="_compute_to_pay_move_lines",
        store=True,
        help="This lines are the ones the user has selected to be paid.",
        copy=False,
        readonly=False,
        check_company=True,
    )
    matched_move_line_ids = fields.Many2many(
        "account.move.line",
        compute="_compute_matched_move_line_ids",
        help="Lines that has been matched to payments, only available after payment validation",
    )
    exchange_diff_move_ids = fields.Many2many(
        "account.move",
        compute="_compute_exchange_diff_move_ids",
        help="Exchange difference journal entries generated when reconciling this payment in foreign currency.",
    )
    exchange_diff_move_count = fields.Integer(
        compute="_compute_exchange_diff_move_ids",
    )
    write_off_type_id = fields.Many2one(
        "account.write_off.type",
        check_company=True,
    )
    write_off_amount = fields.Monetary(
        currency_field="destination_currency_id",
    )
    payment_difference = fields.Monetary(
        compute="_compute_payment_difference",
        string="Payments Difference",
        currency_field="destination_currency_id",
        help="Difference between 'To Pay Amount' and 'Payment Total'",
    )
    write_off_available = fields.Boolean(compute="_compute_write_off_available")
    use_payment_pro = fields.Boolean(compute="_compute_use_payment_pro")
    open_move_line_ids = fields.One2many(related="move_id.open_move_line_ids")
    multi_currency_debt = fields.Boolean(
        compute="_compute_multi_currency_debt",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "previous_currency_id" in fields_list and "previous_currency_id" not in res:
            currency_id = res.get("currency_id")
            if not currency_id:
                journal_id = res.get("journal_id")
                if journal_id:
                    journal = self.env["account.journal"].browse(journal_id)
                    currency_id = (journal.currency_id or journal.company_id.currency_id).id
            if currency_id:
                res["previous_currency_id"] = currency_id
        return res

    @api.depends("to_pay_move_line_ids", "company_id.reconcile_on_company_currency")
    def _compute_multi_currency_debt(self):
        for rec in self:
            if rec.company_id.reconcile_on_company_currency:
                rec.multi_currency_debt = False
                continue
            currencies = rec.to_pay_move_line_ids.mapped("currency_id")
            rec.multi_currency_debt = len(currencies) > 1

    @api.depends(
        "destination_account_id",
        "company_currency_id",
        "company_id",
        "to_pay_move_line_ids",
        "multi_currency_debt",
    )
    @api.depends_context("default_company_id")
    def _compute_counterpart_currency_editable(self):
        for rec in self:
            account_currency = rec.destination_account_id.currency_id
            if account_currency and account_currency != rec.company_currency_id:
                rec.counterpart_currency_editable = False
                continue
            elif self._context.get("default_company_id") and not rec.company_id.reconcile_on_company_currency:
                # sin reconcile, si venimos desde una factura NO queremos que editen la currency
                rec.counterpart_currency_editable = False
                continue
            rec.counterpart_currency_editable = True

    @api.depends(
        "destination_account_id",
        "to_pay_move_line_ids",
        "company_id",
        "company_currency_id",
        "is_internal_transfer",
        "destination_journal_id",
    )
    def _compute_counterpart_currency_id(self):
        for rec in self:
            # Transferencias internas: usar moneda del diario destino para mostrar
            # la cotización cruzada (ej. USD/EUR) en la UI via counterpart_rate
            if rec.is_internal_transfer and rec.destination_journal_id:
                rec.counterpart_currency_id = rec.destination_journal_id.currency_id or rec.company_currency_id
                continue

            account_currency = rec.destination_account_id.currency_id
            company_currency = rec.company_currency_id

            # Caso 1: la cuenta tiene moneda propia distinta a la de la compañía → forzar, no editable
            if account_currency and account_currency != company_currency:
                rec.counterpart_currency_id = account_currency
                continue

            # Caso 2: la cuenta no tiene moneda definida (o es la de la compañía), en reconcile si ya eligió una
            # la mantenemos. Sin reconcile se recomputa porque pudo elegir deuda en otra moneda
            if rec.company_id.reconcile_on_company_currency:
                if not rec.counterpart_currency_id:
                    # Default: moneda de la compañía
                    rec.counterpart_currency_id = company_currency
            elif rec.to_pay_move_line_ids:
                currencies = rec.to_pay_move_line_ids.mapped("currency_id")
                if len(currencies) == 1:
                    rec.counterpart_currency_id = currencies
                else:
                    # Múltiples monedas: ask user to edit
                    rec.counterpart_currency_id = False
            elif not rec.counterpart_currency_id:
                # Sin deuda seleccionada: default moneda de la compañía
                rec.counterpart_currency_id = company_currency

    @api.onchange("counterpart_currency_id")
    def _onchange_counterpart_currency_id_filter_lines(self):
        """Cuando el usuario cambia la moneda de cancelación manualmente,
        filtrar las líneas de deuda para que solo queden las de esa moneda.
        Solo aplica cuando hay líneas con múltiples monedas.
        """
        for rec in self:
            if not rec.counterpart_currency_id:
                continue
            if rec.company_id.reconcile_on_company_currency:
                continue  # con reconcile no filtramos, la moneda es informativa
            # Si todas las líneas ya están en la moneda elegida, el cambio fue
            # computado desde las propias líneas (ej: apertura del wizard desde
            # facturas), no iniciado por el usuario → no hay nada que filtrar.
            if rec.to_pay_move_line_ids:
                line_currencies = rec.to_pay_move_line_ids.mapped("currency_id")
                if len(line_currencies) == 1 and line_currencies == rec.counterpart_currency_id:
                    continue
            rec.with_context(force_currency_domain=rec.counterpart_currency_id.id)._add_all()

    @api.depends("counterpart_currency_id", "company_id", "destination_account_id", "company_currency_id")
    def _compute_destination_currency_id(self):
        for rec in self:
            if not rec.company_id.reconcile_on_company_currency:
                rec.destination_currency_id = rec.counterpart_currency_id
            else:
                dest_currency = rec.destination_account_id.currency_id
                if dest_currency and dest_currency != rec.company_currency_id:
                    rec.destination_currency_id = dest_currency
                else:
                    rec.destination_currency_id = rec.company_currency_id

    @api.depends("currency_id", "company_currency_id", "company_id", "date")
    def _compute_accounting_rate(self):
        for rec in self:
            if not rec.currency_id or rec.currency_id == rec.company_currency_id:
                rec.accounting_rate = 1.0
            else:
                # _get_conversion_rate(from=C, to=A) devuelve A/C, que es el formato Odoo nativo que necesitamos
                rec.accounting_rate = self.env["res.currency"]._get_conversion_rate(
                    from_currency=rec.company_currency_id,
                    to_currency=rec.currency_id,
                    company=rec.company_id,
                    date=rec.date or fields.Date.context_today(rec),
                )

    ####
    # CODIGO para UX de rate según la moneda mas fuerte. TODO evaluar si mantenemos o simplificamos
    ####

    @api.depends("currency_id", "counterpart_currency_id", "company_id", "date")
    def _compute_counterpart_rate_inverted(self):
        """Se fija en el rate teórico A→B1 para determinar si B1 es moneda fuerte (rate < 1.0) y por lo tanto mostrar el rate invertido al usuario (B1→A)"""
        for rec in self:
            if not rec.currency_id or rec.currency_id == rec.counterpart_currency_id:
                rec.counterpart_rate_inverted = False
                continue
            theoretical_rate = self.env["res.currency"]._get_conversion_rate(
                from_currency=rec.currency_id,
                to_currency=rec.counterpart_currency_id,
                company=rec.company_id,
                date=rec.date or fields.Date.context_today(rec),
            )
            rec.counterpart_rate_inverted = theoretical_rate < 1.0

    @api.depends("currency_id", "company_currency_id", "company_id", "date")
    def _compute_accounting_rate_inverted(self):
        """Se fija en el rate teórico A→C para determinar si C es moneda fuerte (rate < 1.0) y por lo tanto mostrar el rate invertido al usuario (C→A)"""
        for rec in self:
            if not rec.currency_id or rec.currency_id == rec.company_currency_id:
                rec.accounting_rate_inverted = False
                continue
            # Misma dirección que _compute_accounting_rate: _get_conversion_rate(C→A) = A/C.
            # Si A/C < 1.0 (A es la moneda fuerte, ej: USD/ARS = 0.000667), mostramos C/A = 1500.
            theoretical_rate = self.env["res.currency"]._get_conversion_rate(
                from_currency=rec.company_currency_id,
                to_currency=rec.currency_id,
                company=rec.company_id,
                date=rec.date or fields.Date.context_today(rec),
            )
            rec.accounting_rate_inverted = theoretical_rate < 1.0

    @api.depends("accounting_rate")
    def _compute_user_accounting_rate(self):
        for rec in self:
            rec.user_accounting_rate = 1.0 / rec.accounting_rate if rec.accounting_rate else 0.0

    @api.onchange("user_accounting_rate")
    def _inverse_user_accounting_rate(self):
        for rec in self:
            rec.accounting_rate = 1.0 / rec.user_accounting_rate if rec.user_accounting_rate else 0.0

    @api.depends("counterpart_rate")
    def _compute_user_counterpart_rate(self):
        for rec in self:
            rec.user_counterpart_rate = 1.0 / rec.counterpart_rate if rec.counterpart_rate else 0.0

    @api.onchange("user_counterpart_rate")
    def _inverse_user_counterpart_rate(self):
        for rec in self:
            if not rec.user_counterpart_rate:
                continue
            rec.counterpart_rate = 1.0 / rec.user_counterpart_rate
            # Propagar a accounting_rate si B1 == C
            if rec.counterpart_currency_id == rec.company_currency_id:
                rec.accounting_rate = (1.0 / rec.counterpart_rate) if rec.counterpart_rate else 1.0

    ####
    # FIN CODIGO para UX de rate según la moneda mas fuerte. TODO evaluar si mantenemos o simplificamos
    ####

    @api.depends("company_id", "outstanding_account_id")
    def _compute_use_payment_pro(self):
        payment_with_pro = self.filtered(lambda x: x.company_id.use_payment_pro and x.outstanding_account_id)
        payment_with_pro.use_payment_pro = True
        (self - payment_with_pro).use_payment_pro = False

    @api.depends("company_id")
    def _compute_write_off_available(self):
        for rec in self:
            rec.write_off_available = bool(
                rec.env["account.write_off.type"].search([("company_ids", "=", rec.company_id.id)], limit=1)
            )

    @api.onchange("amount")
    def _onchange_amount_update_exact(self):
        for rec in self:
            if not rec.currency_id.is_zero(rec.amount - rec.amount_exact):
                rec.amount_exact = rec.amount

    @api.onchange("currency_id")
    def _onchange_currency_recompute_amount(self):
        """Al cambiar la moneda del diario, reconvertir amount a la nueva moneda A."""
        for rec in self:
            new_currency = rec.currency_id
            # previous_currency_id se round-tripea desde el cliente en cada onchange,
            # por eso refleja la moneda real anterior (funciona en registros nuevos y
            # en cambios consecutivos A→B→C sin guardar, donde _origin no sirve).
            old_currency = rec.previous_currency_id or rec._origin.currency_id
            if not old_currency:
                old_currency = rec.company_currency_id
            # Actualizar para el próximo onchange antes de cualquier continue
            rec.previous_currency_id = new_currency
            if rec.state != "draft" or not rec.amount:
                continue

            old_amount = rec.amount_exact or rec.amount
            if not old_amount:
                old_amount = rec.env.context.get("default_amount", 0.0)
            amount = abs(
                old_currency._convert(
                    old_amount,
                    new_currency,
                    rec.company_id,
                    rec.date or fields.Date.context_today(rec),
                    False,
                )
            )
            if (
                rec.env.context.get("default_amount")
                and rec.currency_id == rec.company_currency_id
                and rec.amount_exact == rec._origin.amount_exact
                and not rec.currency_id.is_zero(amount - rec.env.context.get("default_amount"))
            ):
                amount = rec.env.context.get("default_amount")
            rec.update({"amount_exact": amount, "amount": amount})

    @api.constrains("to_pay_move_line_ids")
    def _check_to_pay_lines_account(self):
        """TODO ver si esto tmb lo llevamos a la UI y lo mostramos como un warning.
        tmb podemos dar mas info al usuario en el error"""
        for rec in self.filtered(lambda x: x.partner_id and x.state != "draft"):
            accounts = rec.to_pay_move_line_ids.mapped("account_id")
            if len(accounts) > 1 and not self.env.context.get("default_mode") == "check_balance":
                raise ValidationError(_("To Pay Lines must be of the same account!"))

    @api.constrains("to_pay_move_line_ids", "counterpart_currency_id")
    def _check_to_pay_lines_currency(self):
        for rec in self:
            if rec.company_id.reconcile_on_company_currency:
                continue
            currencies = rec.to_pay_move_line_ids.mapped("currency_id")
            if len(currencies) > 1:
                raise ValidationError(
                    _("All selected debt lines must have the same currency. Found: %s")
                    % ", ".join(currencies.mapped("name"))
                )

    def action_draft(self):
        # Seteamos posted_before en true para que nos permita pasar a borrador el pago y poder realizar cambio sobre el mismo
        # Nos salteamos la siguente validacion
        # https://github.com/odoo/odoo/blob/b6b90636938ae961c339807ea893cabdede9f549/addons/account/models/account_move.py#L2474

        for rec in self.filtered(lambda p: p.company_id.use_payment_pro):
            rec.move_id.posted_before = False

            # Al pasar a borrador un pago, eliminamos las conciliaciones parciales que tenga.
            valid_account_types = rec._get_valid_payment_account_types()
            payment_lines = rec.move_id.line_ids.filtered(lambda l: l.account_id.account_type in valid_account_types)
            partials = payment_lines.mapped("matched_debit_ids") | payment_lines.mapped("matched_credit_ids")
            if partials:
                partials.unlink()

        super().action_draft()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "amount" in vals and "amount_exact" not in vals:
                vals["amount_exact"] = vals["amount"]
        return super().create(vals_list)

    def write(self, vals):
        if "amount" in vals and "amount_exact" not in vals:
            vals["amount_exact"] = vals["amount"]
        for rec in self:
            if rec.company_id.use_payment_pro or (
                "company_id" in vals and rec.env["res.company"].browse(vals["company_id"]).use_payment_pro
            ):
                # Lo siguiente lo evaluamos para evitar la validacion de odoo de
                # https://github.com/odoo/odoo/blob/b6b90636938ae961c339807ea893cabdede9f549/addons/account/models/account_move.py#L2476
                # y permitirnos realizar la modificacion del journal.
                if "journal_id" in vals and rec.journal_id.id != vals["journal_id"]:
                    # Lo agregamos a este cambio por el siguiente campo agregado en
                    #  https://github.com/odoo/odoo/commit/da49c9268b3876a0482a5593379c02418e806b61
                    # De esta forma evitamos el error de asignar un sequence_number de forma random que ademas se estaba recomputando nuevamente,
                    # volviendo a su valor original.
                    rec.move_id.quick_edit_mode = True

                # Lo siguiente lo agregamos para primero obligarnos a cambiar el journal_id y no la company_id. Una vez cambiado el journal_id
                # la company_id se cambia correctamente.
                if "company_id" in vals and "journal_id" in vals:
                    rec.move_id.journal_id = vals["journal_id"]
        return super().write(vals)

    ##############################
    # desde modelo account.payment
    ##############################

    # TODO re-evaluar. tal vez mejor esto en un modulo multicompany?
    # @api.depends('payment_type')
    # def _compute_available_journal_ids(self):
    #     """
    #     Este metodo odoo lo agrega en v16
    #     Igualmente nosotros lo modificamos acá para que funcione con esta logica:
    #     a) desde transferencias permitir elegir cualquier diario ya que no se selecciona compañía
    #     b) desde grupos de pagos solo permitir elegir diarios de la misma compañía
    #     NOTA: como ademas estamos mandando en el contexto del company_id, tal vez podriamos evitar pisar este metodo
    #     y ande bien en v16 para que las lineas de pago de un payment group usen la compañia correspondiente, pero
    #     lo que faltaria es hacer posible en las transferencias seleccionar una compañia distinta a la por defecto
    #     """
    #     journals = self.env['account.journal'].search([
    #         ('company_id', 'in', self.env.companies.ids), ('type', 'in', ('bank', 'cash'))
    #     ])
    #     for pay in self:
    #         filtered_domain = [('inbound_payment_method_line_ids', '!=', False)] if \
    #             pay.payment_type == 'inbound' else [('outbound_payment_method_line_ids', '!=', False)]
    #         pay.available_journal_ids = journals.filtered_domain(filtered_domain)

    # agreamos depends de company para que re calcule los diarios disponibles
    @api.depends("company_id")
    def _compute_available_journal_ids(self):
        if self.company_id:
            self = self.with_company(self.company_id.id)
        super(AccountPayment, self)._compute_available_journal_ids()

    @api.depends("amount", "counterpart_rate", "counterpart_currency_id", "currency_id")
    def _compute_counterpart_currency_amount(self):
        for rec in self:
            amount = rec.amount_exact or rec.amount
            if rec.counterpart_currency_id and rec.counterpart_currency_id != rec.currency_id:
                if rec.counterpart_rate:
                    # amount está en A, convertir a B1 usando counterpart_rate
                    rec.counterpart_currency_amount = amount * rec.counterpart_rate
                else:
                    rec.counterpart_currency_amount = 0.0
            else:
                # A == B1, son la misma moneda
                rec.counterpart_currency_amount = amount

    @api.onchange("counterpart_currency_amount")
    def _inverse_counterpart_currency_amount(self):
        for rec in self:
            # Usar amount_exact para comparación precisa
            amount_to_compare = rec.amount_exact if rec.amount_exact else rec.amount
            if rec.counterpart_currency_id and not rec.counterpart_currency_id.is_zero(
                amount_to_compare * rec.counterpart_rate - rec.counterpart_currency_amount
            ):
                # Usar amount_exact para cálculo preciso sin pérdida de decimales
                if rec.counterpart_rate:
                    exact_amount = rec.counterpart_currency_amount / rec.counterpart_rate
                    rec.amount_exact = exact_amount
                    rec.amount = exact_amount
                else:
                    rec.amount_exact = 0
                    rec.amount = 0

    @api.depends(
        "accounting_rate", "counterpart_currency_id", "currency_id", "company_currency_id", "company_id", "date"
    )
    def _compute_counterpart_rate(self):
        for rec in self:
            if not rec.counterpart_currency_id:
                rec.counterpart_rate = 1.0
                continue

            # Caso B1 == C: counterpart_rate = B1/A = C/A = 1/accounting_rate
            # accounting_rate = A/C, por lo que counterpart_rate es su inversa
            if rec.counterpart_currency_id == rec.company_currency_id:
                rec.counterpart_rate = (1.0 / rec.accounting_rate) if rec.accounting_rate else 1.0
                continue

            # Caso A == B1: sin conversión
            if rec.currency_id == rec.counterpart_currency_id:
                rec.counterpart_rate = 1.0
                continue

            # Caso general A != B1 != C
            rec.counterpart_rate = self.env["res.currency"]._get_conversion_rate(
                from_currency=rec.currency_id,
                to_currency=rec.counterpart_currency_id,
                company=rec.company_id,
                date=rec.date or fields.Date.context_today(rec),
            )

    @api.onchange("counterpart_rate")
    def _inverse_counterpart_rate(self):
        for rec in self:
            if rec.counterpart_currency_id == rec.company_currency_id:
                # counterpart_rate = B1/A = C/A = 1/accounting_rate → accounting_rate = 1/counterpart_rate
                rec.accounting_rate = (1.0 / rec.counterpart_rate) if rec.counterpart_rate else 1.0

    @api.depends("to_pay_move_line_ids")
    def _compute_destination_account_id(self):
        """
        If we are paying a payment gorup with paylines, we use account
        of lines that are going to be paid
        """
        for rec in self:
            to_pay_account = rec.to_pay_move_line_ids.mapped("account_id")
            if to_pay_account:
                # tomamos la primer si hay mas de una, luego en el post si la deuda se intenta conciliar odoo
                # devuelve error. No lo protegemos acá por estas razones:
                # 1. el boton add all no se podria usar porque ya hace un write y el usuario deberia elegir a mano los apuntes
                # 2. le vamos a dar error al usuario en algunos casos sin que sea necesario ya que luego, si el importe es menor
                # no llega a intentar conciliarse con est epago
                rec.destination_account_id = to_pay_account[0]
            else:
                super(AccountPayment, rec)._compute_destination_account_id()

    def _prepare_move_lines_per_type(self, write_off_line_vals=None, force_balance=None):
        if not self.company_id.use_payment_pro:
            # Para pagos sin ppro que tengan accounting rate, forzamos el balance
            # para que no haya diferencias en el asiento
            if self.accounting_rate and self.currency_id != self.company_currency_id and force_balance is None:
                amount_for_calc = self.amount_exact if self.amount_exact else self.amount
                force_balance = amount_for_calc / self.accounting_rate  # A/C → monto en C
            return super()._prepare_move_lines_per_type(
                write_off_line_vals=write_off_line_vals, force_balance=force_balance
            )

        # Write-off en moneda B2 (destination_currency_id)
        write_off_line_vals = []
        if self.write_off_amount and self.write_off_type_id:
            wo_sign = 1 if self.payment_type == "inbound" else -1
            wo_amount = wo_sign * self.write_off_amount
            wo_balance = self.destination_currency_id._convert(
                wo_amount, self.company_currency_id, self.company_id, self.date
            )
            write_off_line_vals.append(
                {
                    "name": self.write_off_type_id.label or self.write_off_type_id.name,
                    "account_id": self.write_off_type_id.account_id.id,
                    "partner_id": self.partner_id.id,
                    "currency_id": self.destination_currency_id.id,
                    "amount_currency": wo_amount,
                    "balance": wo_balance,
                }
            )

        res = super()._prepare_move_lines_per_type(write_off_line_vals=write_off_line_vals, force_balance=force_balance)

        # ── Re-inyectar write-off si base Odoo lo descartó ────────────────────────
        # Base Odoo (L342-345) descarta write_off_lines cuando hay withholding_lines
        # porque asume que las retenciones se pasan como write-off en _synchronize_to_moves.
        # En payment_pro las retenciones y el write-off son conceptos separados, así que
        # re-inyectamos las write-off lines que nosotros construimos.
        if write_off_line_vals and not res.get("write_off_lines"):
            res["write_off_lines"] = write_off_line_vals

        liquidity_lines = res.get("liquidity_lines", [])
        counterpart_lines = res.get("counterpart_lines", [])

        if not liquidity_lines or not counterpart_lines:
            return res

        # ── Ajuste de las líneas de LIQUIDEZ ──────────────────────────────────────
        # accounting_rate = A/C (formato Odoo nativo, ej: 0.000667 p/USD→ARS)
        # balance_en_C = amount_en_A / accounting_rate
        # Se itera sobre TODAS las líneas (puede haber N cuando se usan cheques)
        # Cuando force_balance está definido, el balance ya fue forzado por base Odoo
        # (ej: paired payment de transferencia interna) y NO debe recalcularse.
        if self.accounting_rate and self.currency_id != self.company_currency_id and force_balance is None:
            # Usar amount_exact si está disponible para evitar desbalances por redondeo.
            # Cuando hay una sola línea de liquidez, usamos amount_exact directamente.
            # Cuando hay múltiples líneas (cheques), usamos el amount_currency de cada una.
            if len(liquidity_lines) == 1 and self.amount_exact and self.amount_exact != self.amount:
                amount_for_balance = self.amount_exact
                liq_sign = 1 if liquidity_lines[0]["amount_currency"] >= 0 else -1
                liquidity_lines[0]["amount_currency"] = liq_sign * abs(amount_for_balance)
                liquidity_lines[0]["balance"] = liquidity_lines[0]["amount_currency"] / self.accounting_rate
            else:
                for liq_line in liquidity_lines:
                    liq_line["balance"] = liq_line["amount_currency"] / self.accounting_rate

        # ── Recalcular balance de CONTRAPARTIDA para cerrar el asiento ────────────
        write_off_balance = sum(line["balance"] for line in res.get("write_off_lines", []))
        withholding_balance = sum(line["balance"] for line in res.get("withholding_lines", []))
        total_liq_balance = sum(line["balance"] for line in liquidity_lines)
        counterpart_lines[0]["balance"] = -total_liq_balance - write_off_balance - withholding_balance

        # ── Ajuste de MONEDA en la línea de CONTRAPARTIDA ─────────────────────────
        if self.is_internal_transfer:
            # Transferencia interna: la línea de cuenta puente va siempre en moneda
            # de compañía (C) para que ambos lados (original y paired) reconcilien
            # correctamente en amount_currency y balance.
            counterpart_lines[0].update(
                {
                    "currency_id": self.company_currency_id.id,
                    "amount_currency": counterpart_lines[0]["balance"],
                }
            )
        elif self.counterpart_currency_id and self.counterpart_currency_id != self.currency_id:
            # Si A != B1: la contrapartida va en moneda B1 (counterpart_currency_id)
            cp_sign = 1 if counterpart_lines[0].get("amount_currency", 0) >= 0 else -1
            # La contrapartida AP/AR cubre el TOTAL de la deuda cancelada: cash + write-off.
            # counterpart_currency_amount = porción cash en B1, write_off_amount está en B2.
            # Cuando B1 == B2 (caso estándar sin reconcile_on_company_currency) sumamos directo.
            counterpart_amt = abs(self.counterpart_currency_amount)
            if self.write_off_amount and self.destination_currency_id == self.counterpart_currency_id:
                counterpart_amt += abs(self.write_off_amount)
            counterpart_lines[0].update(
                {
                    "currency_id": self.counterpart_currency_id.id,
                    "amount_currency": cp_sign * counterpart_amt,
                }
            )
        # Si A == B1: la moneda ya es correcta (A), solo el balance se actualizó arriba

        return res

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        # api.model hack: evita error en la creación de un payment donde se hace un write
        # que llama a este método antes de que exista move_id
        if self.mapped("move_id"):
            res = res + (
                "accounting_rate",
                "counterpart_rate",
                "counterpart_currency_id",
            )
        return res + (
            "write_off_amount",
            "write_off_type_id",
        )

    def _prepare_paired_payment_values(self):
        vals = super()._prepare_paired_payment_values()
        # counterpart_currency_id del paired = moneda del journal original.
        # Lo pasamos explícitamente porque copy() copia el valor del original
        # y al ser store=True + readonly=False el compute no se re-dispara.
        vals["counterpart_currency_id"] = self.currency_id.id
        dest_currency = self.destination_journal_id.currency_id or self.company_currency_id
        if dest_currency != self.currency_id:
            # balance_in_c: monto en moneda de compañía (ARS)
            # Usar amount_exact para cálculos precisos
            amount_for_calc = self.amount_exact if self.amount_exact else self.amount
            if self.accounting_rate and self.currency_id != self.company_currency_id:
                balance_in_c = amount_for_calc / self.accounting_rate
            else:
                balance_in_c = amount_for_calc

            if dest_currency == self.counterpart_currency_id and self.counterpart_currency_amount:
                # counterpart_currency_id coincide con la moneda destino (caso habitual
                # en transferencias internas). Usamos counterpart_currency_amount que
                # respeta cualquier cotización cruzada editada por el usuario.
                paired_amount = abs(self.counterpart_currency_amount)
            elif dest_currency == self.company_currency_id:
                paired_amount = balance_in_c
            else:
                # Fallback: convertir pasando por C (moneda contable)
                dest_rate = self.env["res.currency"]._get_conversion_rate(
                    self.company_currency_id,
                    dest_currency,
                    self.company_id,
                    self.date or fields.Date.context_today(self),
                )
                paired_amount = dest_currency.round(balance_in_c * dest_rate)

            vals["amount_exact"] = paired_amount
            vals["amount"] = paired_amount

            # counterpart_currency_amount del paired = monto original (cuánto
            # salió del journal original). Lo pasamos explícitamente porque copy()
            # copia el valor del original y al tener inverse= el ORM ejecuta el
            # inverse durante create, sobreescribiendo amount.
            vals["counterpart_currency_amount"] = self.amount_exact if self.amount_exact else self.amount

            # Fijar accounting_rate del paired para que refleje la tasa implícita
            # real de la operación (balance_in_c / paired_amount), no la del día.
            if dest_currency != self.company_currency_id and balance_in_c:
                vals["accounting_rate"] = paired_amount / balance_in_c

            # Fijar counterpart_rate del paired: la contraparte del paired es la
            # moneda del journal original (B1_paired = self.currency_id).
            # rate = original_amount / paired_amount = B1/A del paired.
            if paired_amount:
                vals["counterpart_rate"] = (self.amount_exact if self.amount_exact else self.amount) / paired_amount

        return vals

    ####################################
    # desde modelo account.payment.group
    ####################################

    @api.depends("move_id.line_ids")
    def _compute_matched_move_line_ids(self):
        """
        Las partial reconcile vinculan dos apuntes con credit_move_id y
        debit_move_id.
        Buscamos primeros todas las que tienen en credit_move_id algun apunte
        de los que se genero con un pago, etnonces la contrapartida
        (debit_move_id), son cosas que se pagaron con este pago. Repetimos
        al revz (debit_move_id vs credit_move_id)
        El depends en account de odoo para casos similares usa
        @api.depends('move_id.line_ids.matched_debit_ids', 'move_id.line_ids.matched_credit_ids')
        Aca preferimos mantener  move_id.line_ids por cuestiones de performace.
        Si _compute_matched_move_line_ids fuera stored cambiariamos el depend
        TODO v18, ver si podemos reutilizar reconciled_invoice_ids y/o reconciled_bill_ids
        al menos podremos re-usar codigo sql para optimizar performance
        Por ahora no lo estamos usando porque el actual código de odoo solo muestra facturas o algo así (por ej. si hay
        conciliacion de deuda de un asiento normal no lo muestra)
        """
        stored_payments = self.filtered("id")
        for rec in stored_payments:
            payment_lines = rec.move_id.line_ids.filtered(
                lambda x: x.account_type in self._get_valid_payment_account_types()
            )
            debit_moves = payment_lines.mapped("matched_debit_ids.debit_move_id")
            credit_moves = payment_lines.mapped("matched_credit_ids.credit_move_id")

            # Excluimos los apuntes que pertenecen a asientos de diferencia de cambio
            # (generados automáticamente por Odoo al conciliar en moneda extranjera).
            # Razones:
            #   1. Son inconsistentes: si la cotización baja se generan con signo opuesto
            #      y algunos aparecen mientras otros no, según la dirección del movimiento.
            #   2. No aportan información al informe que se entrega al cliente; el cliente
            #      quiere ver los comprobantes reales que se cancelaron, no los ajustes internos.
            #
            # Usamos account.partial.reconcile.exchange_move_id, que es el vínculo directo
            # entre cada conciliación parcial y el asiento de diferencia que generó. Es más
            # preciso que filtrar por diario de diferencias: no depende de configuración y no
            # excluye por azar asientos legítimos contabilizados en ese diario.
            #
            # Los asientos excluidos se exponen en `exchange_diff_move_ids` para uso
            # contable/backend (ver campo y botón inteligente en la vista).
            exchange_move_ids = payment_lines.mapped("matched_debit_ids.exchange_move_id") | payment_lines.mapped(
                "matched_credit_ids.exchange_move_id"
            )
            if exchange_move_ids:
                debit_moves = debit_moves.filtered(lambda x: x.move_id not in exchange_move_ids)
                credit_moves = credit_moves.filtered(lambda x: x.move_id not in exchange_move_ids)

            debit_lines_sorted = debit_moves.filtered(lambda x: x.date_maturity != False).sorted(
                key=lambda x: (x.date_maturity, x.move_id.name)
            )
            credit_lines_sorted = credit_moves.filtered(lambda x: x.date_maturity != False).sorted(
                key=lambda x: (x.date_maturity, x.move_id.name)
            )
            debit_lines_without_date_maturity = debit_moves - debit_lines_sorted
            credit_lines_without_date_maturity = credit_moves - credit_lines_sorted
            rec.matched_move_line_ids = (
                (debit_lines_sorted + debit_lines_without_date_maturity)
                | (credit_lines_sorted + credit_lines_without_date_maturity)
            ) - payment_lines

        (self - stored_payments).matched_move_line_ids = False

    def _compute_exchange_diff_move_ids(self):
        """Recolecta todos los asientos de diferencia de cambio vinculados a este pago
        via account.partial.reconcile.exchange_move_id.

        A diferencia de matched_move_line_ids (que los excluye), este campo los expone
        todos — tanto los de cotización al alza como a la baja — para uso contable.
        """
        stored_payments = self.filtered("id")
        for rec in stored_payments:
            payment_lines = rec.move_id.line_ids.filtered(
                lambda x: x.account_type in self._get_valid_payment_account_types()
            )
            moves = payment_lines.mapped("matched_debit_ids.exchange_move_id") | payment_lines.mapped(
                "matched_credit_ids.exchange_move_id"
            )
            rec.exchange_diff_move_ids = moves
            rec.exchange_diff_move_count = len(moves)
        (self - stored_payments).exchange_diff_move_ids = False
        (self - stored_payments).exchange_diff_move_count = 0

    def action_open_exchange_diff_moves(self):
        """Abre los asientos de diferencia de cambio relacionados con este pago."""
        self.ensure_one()
        list_view_id = self.env.ref("account.view_move_tree").id
        form_view_id = self.env.ref("account.view_move_form").id
        return {
            "type": "ir.actions.act_window",
            "name": _("Exchange Differences"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "views": [(list_view_id, "list"), (form_view_id, "form")],
            "domain": [("id", "in", self.exchange_diff_move_ids.ids)],
        }

    @api.depends("state", "matched_move_line_ids", "payment_total")
    def _compute_matched_amounts(self):
        for rec in self:
            rec.matched_amount = 0.0
            rec.unmatched_amount = 0.0
            if rec.state == "draft":
                continue
            sign = rec.payment_type == "outbound" and -1.0 or 1.0
            rec.matched_amount = sign * sum(
                rec.matched_move_line_ids.with_context(matched_payment_ids=rec.ids).mapped("payment_matched_amount")
            )
            rec.unmatched_amount = abs(rec.payment_total) - rec.matched_amount

    @api.depends("to_pay_move_line_ids")
    def _compute_has_outstanding(self):
        for rec in self:
            rec.has_outstanding = False
            if rec.state != "draft":
                continue
            if rec.partner_type == "supplier":
                lines = rec.to_pay_move_line_ids.filtered(lambda x: x.amount_residual > 0.0)
            else:
                lines = rec.to_pay_move_line_ids.filtered(lambda x: x.amount_residual < 0.0)
            if len(lines) != 0:
                rec.has_outstanding = True

    @api.depends(
        "counterpart_currency_amount",
        "write_off_amount",
        "amount",
        "accounting_rate",
        "counterpart_currency_id",
        "destination_currency_id",
    )
    def _compute_payment_total(self):
        for rec in self:
            if rec.counterpart_currency_id == rec.destination_currency_id:
                # B1 == B2 (caso normal sin reconcile): cca ya está en B2.
                # Aplica tanto si A != C (journal en moneda extranjera) como si A == C
                # (journal en moneda de compañía), porque counterpart_currency_amount
                # siempre está expresado en B1 = B2 = destination_currency_id.
                base_amount = rec.counterpart_currency_amount
            else:
                # B1 != B2 (reconcile_on_company_currency): B2 = C siempre
                # Convertir A → C = amount_exact / accounting_rate (usar amount_exact para evitar redondeos)
                amount_for_calc = rec.amount_exact if rec.amount_exact else rec.amount
                base_amount = amount_for_calc / rec.accounting_rate if rec.accounting_rate else amount_for_calc
                base_amount = rec.amount / rec.accounting_rate if rec.accounting_rate else rec.amount
            rec.payment_total = base_amount + rec.write_off_amount

    # TODO revisar depends
    @api.depends("payment_total", "to_pay_amount")
    def _compute_payment_difference(self):
        for rec in self:
            rec.payment_difference = rec.to_pay_amount - rec.payment_total

    def _get_payment_difference_in_currency_a(self):
        """Convierte payment_difference (B2) a moneda A (currency_id del pago)."""
        self.ensure_one()
        if self.counterpart_currency_id != self.destination_currency_id:
            # B1 ≠ B2 (reconcile): B2=C siempre → C→A = diff * accounting_rate
            return self.payment_difference * (self.accounting_rate or 1.0)
        else:
            # B1 = B2: counterpart_rate = B1/A → A = diff / counterpart_rate
            counterpart = self.counterpart_rate or 1.0
            return self.payment_difference / counterpart if counterpart else self.payment_difference

    def action_adjust_amount_for_difference(self):
        """Ajusta amount para que payment_difference quede en cero."""
        for rec in self:
            if not rec.payment_difference:
                continue
            diff_in_a = rec._get_payment_difference_in_currency_a()
            amount = rec.amount_exact + diff_in_a
            # No permitir valores negativos, pero mantener el valor actual si el ajuste resulta negativo
            if amount > 0:
                rec.amount_exact = amount
                rec.amount = amount

    def action_adjust_writeoff_for_difference(self):
        """Ajusta write_off_amount para que payment_difference quede en cero."""
        for rec in self:
            if not rec.payment_difference:
                continue
            rec.write_off_amount += rec.payment_difference

    # En el pasado se contaba con to_pay_move_line_ids.amount_residual dentro de los depends,  y no deberiamos por cuestiones de performance, ya que ademas no era necesario
    @api.depends("to_pay_move_line_ids", "destination_currency_id", "payment_type")
    def _compute_selected_debt(self):
        for rec in self:
            # Usamos payment_type (no partner_type) porque cubre tanto los casos normales
            # (outbound+supplier, inbound+customer) como los invertidos (outbound+customer,
            # inbound+supplier). amount_residual es negativo para créditos y positivo para
            # débitos; multiplicar por -1 en outbound normaliza ambos a positivo.
            sign = -1.0 if rec.payment_type == "outbound" else 1.0
            if rec.destination_currency_id and rec.destination_currency_id != rec.company_currency_id:
                amount = sum(rec.to_pay_move_line_ids._origin.mapped("amount_residual_currency"))
            else:
                amount = sum(rec.to_pay_move_line_ids._origin.mapped("amount_residual"))
            rec.selected_debt = amount * sign

    @api.depends("selected_debt", "unreconciled_amount")
    def _compute_to_pay_amount(self):
        for rec in self:
            rec.to_pay_amount = rec.selected_debt + rec.unreconciled_amount

    @api.onchange("to_pay_amount")
    def _inverse_to_pay_amount(self):
        for rec in self:
            # agregamos este chequeo porque cuando estamos creando un pago nuevo se llama este inverse siempre
            # y si el monto no cambio no queremos que trigeree re computo de retenciones
            # (por el depends de _compute_base_amount)
            if rec.currency_id and not rec.currency_id.is_zero(
                rec.unreconciled_amount - (rec.to_pay_amount - rec.selected_debt)
            ):
                rec.unreconciled_amount = rec.to_pay_amount - rec.selected_debt

    @api.onchange("to_pay_move_line_ids")
    def _onchange_to_pay_lines_adjust_amount(self):
        """Ajustar amount para que payment_total cubra to_pay_amount a la tasa de hoy.
        Cuando action_register_payment envía default_amount basado en amount_residual,
        ese monto usa la tasa original de la factura, no la de hoy. Esto genera un
        payment_difference que debe corregirse ajustando amount.
        Aplica a todos los tipos de pago (clientes y proveedores).
        """
        for rec in self:
            if not rec.use_payment_pro or rec.state != "draft":
                continue
            if not rec.to_pay_move_line_ids:
                continue
            if not rec.payment_difference or not rec.currency_id:
                continue
            diff_in_a = rec._get_payment_difference_in_currency_a()
            amount = rec.amount + diff_in_a
            rec.amount = amount if amount > 0 else 0

    @api.onchange("l10n_latam_new_check_ids")
    def _onchange_new_check_default_amount(self):
        """Al agregar un cheque nuevo, calcular su monto como la diferencia pendiente de pago."""
        if not self.use_payment_pro or self.state != "draft":
            return
        if not self.to_pay_move_line_ids or not self.payment_difference:
            return
        for check in self.l10n_latam_new_check_ids:
            if not check.amount:
                diff_in_a = self._get_payment_difference_in_currency_a()
                if diff_in_a > 0:
                    check.amount = self.currency_id.round(diff_in_a)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self._origin.company_id and self.company_id != self._origin.company_id and self.state == "draft":
            self.remove_all()

    # We dont set 'is_internal_transfer' as a dependencies as it could leed to recompute to_pay_move_line_ids
    @api.depends("partner_id", "partner_type", "company_id")
    def _compute_to_pay_move_lines(self):
        # TODO ?
        # # if payment group is being created from a payment we dont want to compute to_pay_move_lines
        # if self.env.context.get('created_automatically'):
        #     return
        # Se recomputan las lienas solo si la deuda que esta seleccionada solo si
        # cambio el partner, compania o partner_type
        records = self.filtered(lambda x: x.state == "draft")
        internal_transfers = records.filtered(lambda x: x.is_internal_transfer)

        with_payment_pro = self._get_filter_payments(records, ["direct_debit_mandate_id", "pos_session_id"])

        if internal_transfers or not self.env.context.get("pay_now"):
            ((internal_transfers or self) - with_payment_pro).to_pay_move_line_ids = [Command.clear()]
        for rec in with_payment_pro:
            rec._add_all()

    def _get_filter_payments(self, records, extra_fields):
        records = records.filtered(
            lambda x: x.company_id.use_payment_pro and not x.is_internal_transfer and not x.payment_transaction_id
        )

        for field in extra_fields:
            if records._fields.get(field):
                records = records.filtered(lambda x, f=field: not getattr(x, f))

        return records

    def _get_to_pay_move_lines_domain(self):
        self.ensure_one()
        # Cuando se llama desde action_add_all (manual), permitir líneas sin partner
        # Cuando se llama desde _compute_to_pay_move_lines (automático), solo con partner
        if not self.partner_id and not self.env.context.get("include_lines_without_partner"):
            return [(0, "=", 1)]

        domain = [
            ("partner_id", "=", self.partner_id.commercial_partner_id.id),
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "posted"),
            ("account_id.reconcile", "=", True),
            ("reconciled", "=", False),
            ("full_reconcile_id", "=", False),
            (
                "account_id.account_type",
                "=",
                "asset_receivable" if self.partner_type == "customer" else "liability_payable",
            ),
        ]
        if self.env.context.get("force_currency_domain"):
            domain += [("currency_id", "=", self.env.context.get("force_currency_domain"))]
        return domain

    def _add_all(self):
        for rec in self:
            rec.to_pay_move_line_ids = [
                Command.clear(),
                Command.set(self.env["account.move.line"].search(rec._get_to_pay_move_lines_domain()).ids),
            ]

    def action_add_all(self):
        ctx = {}
        if self.counterpart_currency_id and not self.company_id.reconcile_on_company_currency:
            ctx["force_currency_domain"] = self.counterpart_currency_id.id
        self.with_context(active_ids=False, include_lines_without_partner=True, **ctx)._add_all()

    def remove_all(self):
        self.to_pay_move_line_ids = False

    @api.constrains("partner_id", "to_pay_move_line_ids")
    def check_to_pay_lines(self):
        for rec in self:
            to_pay_partners = rec.to_pay_move_line_ids.mapped("partner_id")
            if len(to_pay_partners) > 1:
                raise ValidationError(_("All to pay lines must be of the same partner"))
            if len(rec.to_pay_move_line_ids.mapped("company_id")) > 1:
                raise ValidationError(_("You can't create payments for entries belonging to different companies."))
            if to_pay_partners and to_pay_partners != rec.partner_id.commercial_partner_id:
                raise ValidationError(
                    _("Payment is for partner %s but payment lines are of partner %s")
                    % (rec.partner_id.name, to_pay_partners.name)
                )

    def _reconcile_after_post(self):
        for rec in self.filtered(lambda x: x.company_id.use_payment_pro and not x.is_internal_transfer):
            counterpart_aml = rec.mapped("move_id.line_ids").filtered(
                lambda r: not r.reconciled and r.account_id.account_type in self._get_valid_payment_account_types()
            )
            debt_aml = rec.to_pay_move_line_ids.filtered(
                lambda r: not r.reconciled and r.account_id.id == counterpart_aml.account_id.id
            )
            if counterpart_aml and debt_aml:
                (counterpart_aml + (debt_aml)).reconcile()

    def action_post(self):
        res = super().action_post()
        self._check_to_pay_lines_account()
        self._reconcile_after_post()
        return res

    def _get_mached_payment(self):
        return self.ids

    # --- ORM METHODS--- #
    def export_data(self, fields_to_export):
        """Fix context loss during export for matched/unmatched amounts.
        Pre-calculate values with correct context, then override in export result.
        """
        if any(field in fields_to_export for field in ["matched_amount", "unmatched_amount"]):
            self.invalidate_recordset(["matched_amount", "unmatched_amount"])

            # Pre-calculate with individual context
            values_by_payment = {}
            for payment in self:
                payment.invalidate_recordset(["matched_amount", "unmatched_amount"])
                payment_with_context = payment.with_context(matched_payment_ids=payment.ids)
                values_by_payment[payment.id] = {
                    "matched_amount": payment_with_context.matched_amount,
                    "unmatched_amount": payment_with_context.unmatched_amount,
                }

            result = super().export_data(fields_to_export)

            # Override with correct values
            matched_idx = fields_to_export.index("matched_amount") if "matched_amount" in fields_to_export else None
            unmatched_idx = (
                fields_to_export.index("unmatched_amount") if "unmatched_amount" in fields_to_export else None
            )

            for idx, payment in enumerate(self):
                if matched_idx is not None:
                    result["datas"][idx][matched_idx] = values_by_payment[payment.id]["matched_amount"]
                if unmatched_idx is not None:
                    result["datas"][idx][unmatched_idx] = values_by_payment[payment.id]["unmatched_amount"]

            return result

        return super().export_data(fields_to_export)

    def web_read(self, specification):
        fields_to_read = list(specification) or ["id"]
        if "matched_move_line_ids" in fields_to_read and "context" in specification["matched_move_line_ids"]:
            specification["matched_move_line_ids"]["context"].update(
                {"matched_payment_ids": self._get_mached_payment()}
            )
        return super().web_read(specification)

    @api.depends("journal_id")
    def _compute_available_partner_bank_ids(self):
        super()._compute_available_partner_bank_ids()

    ### FIX RELATIVO A https://github.com/odoo/odoo/pull/212762
    # evitamos agregar pr de odoo, lo hacemos en pay pro que es donde lo necesitamos
    # hasta 18 lo tenemos como pr agregado en odoo
    ###
    # En Odoo 19, get_depends() recorre TODO el MRO via resolve_mro() y acumula _depends
    # de cada clase. Ni @api.depends() vacío ni asignar func._depends = () en la función
    # logran anular los depends del padre porque el padre sigue siendo procesado.
    # La única forma de cortocircuitar resolve_mro es declarar depends=[] en la definición
    # del campo: cuando field._depends is not None, get_depends() retorna inmediatamente
    # sin llamar a resolve_mro().
    company_id = fields.Many2one(depends=[])

    @api.onchange("journal_id")
    def _onchange_journal_id_company_id(self):
        self._compute_company_id()

    # sugerencia de copilot, pero como hasta 18 no lo tenemos, por ahora no implementamos
    # def write(self, vals):
    #     # Forzar recompute solo cuando journal_id cambia en write masivo si es necesario
    #     if 'journal_id' in vals:
    #         self = self.with_context(force_company_recompute=True)
    #     return super().write(vals)

    ### FIN FIX RELATIVO A

    @api.constrains("journal_id", "move_id")
    def _check_payment_move_journal_consistency(self):
        for rec in self.filtered(lambda x: x.move_id and x.move_id.state not in ["draft", "cancel"]):
            if rec.journal_id != rec.move_id.journal_id:
                raise ValidationError(_("The payment journal must match the journal of its journal entry."))
