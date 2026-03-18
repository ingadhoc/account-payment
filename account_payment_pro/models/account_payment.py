from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # Modelo tri-monetario: A (currency_id), B1 (counterpart_currency_id), B2 (destination_currency_id), C (company_currency_id)
    # desde account_payment_group, modelo account.payment
    counterpart_currency_amount = fields.Monetary(
        currency_field="destination_currency_id",
        compute="_compute_counterpart_currency_amount",
        inverse="_inverse_counterpart_currency_amount",
        store=True,
        readonly=False,
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
        inverse="_inverse_accounting_rate",
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
        store=False,
        digits=0,
        min_display_digits=2,
    )
    user_counterpart_rate = fields.Float(
        compute="_compute_user_counterpart_rate",
        inverse="_inverse_user_counterpart_rate",
        store=False,
        digits=0,
        min_display_digits=2,
    )
    counterpart_rate_inverted = fields.Boolean(
        compute="_compute_counterpart_rate_inverted",
        store=False,
        help="True si el rate teórico A→B1 < 1.0 (B1 es la moneda fuerte). "
        "Determina la dirección de visualización de user_counterpart_rate.",
    )
    accounting_rate_inverted = fields.Boolean(
        compute="_compute_accounting_rate_inverted",
        store=False,
        help="True si el rate teórico A→C < 1.0 (C es la moneda fuerte). "
        "Determina la dirección de visualización de user_accounting_rate.",
    )
    journal_currency_id = fields.Many2one(related="journal_id.currency_id", string="Journal Currency")
    destination_journal_currency_id = fields.Many2one(
        related="destination_journal_id.currency_id",
        string="Destination Journal Currency",
    )
    commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    payment_total = fields.Monetary(
        compute="_compute_payment_total",
        tracking=True,
        currency_field="destination_currency_id",
    )
    to_pay_amount_company_currency = fields.Monetary(
        compute="_compute_to_pay_amount_company_currency",
        currency_field="company_currency_id",
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

    @api.depends(
        "destination_account_id",
        "destination_account_id.currency_id",
        "to_pay_move_line_ids",
        "company_id",
        "company_currency_id",
    )
    def _compute_counterpart_currency_id(self):
        for rec in self:
            account_currency = rec.destination_account_id.currency_id
            company_currency = rec.company_currency_id

            # Caso 1: la cuenta tiene moneda propia distinta a la de la compañía → forzar, no editable
            if account_currency and account_currency != company_currency:
                rec.counterpart_currency_id = account_currency
                continue

            # Caso 2: la cuenta no tiene moneda definida (o es la de la compañía)
            # → editable por el usuario; solo asignamos default si no hay valor previo
            if rec.counterpart_currency_id:
                # El usuario ya tiene un valor: respetarlo
                continue

            if rec.company_id.reconcile_on_company_currency:
                # Default: moneda de la compañía
                rec.counterpart_currency_id = company_currency
            elif rec.to_pay_move_line_ids:
                # Default: moneda de las líneas de deuda (todas iguales por constraint)
                rec.counterpart_currency_id = rec.to_pay_move_line_ids[:1].currency_id
            else:
                # Sin deuda seleccionada: default moneda de la compañía
                rec.counterpart_currency_id = company_currency

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

    def _inverse_accounting_rate(self):
        # El valor se setea directamente por el usuario o por user_accounting_rate inverse
        pass

    @api.depends("currency_id", "counterpart_currency_id", "company_id", "date")
    def _compute_counterpart_rate_inverted(self):
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
        for rec in self:
            if not rec.currency_id or rec.currency_id == rec.company_currency_id:
                rec.accounting_rate_inverted = False
                continue
            theoretical_rate = self.env["res.currency"]._get_conversion_rate(
                from_currency=rec.currency_id,
                to_currency=rec.company_currency_id,
                company=rec.company_id,
                date=rec.date or fields.Date.context_today(rec),
            )
            rec.accounting_rate_inverted = theoretical_rate < 1.0

    @api.depends("accounting_rate", "accounting_rate_inverted")
    def _compute_user_accounting_rate(self):
        for rec in self:
            rate = rec.accounting_rate
            if not rate:
                rec.user_accounting_rate = 0.0
            elif rec.accounting_rate_inverted:
                rec.user_accounting_rate = 1.0 / rate
            else:
                rec.user_accounting_rate = rate

    @api.onchange("user_accounting_rate")
    def _inverse_user_accounting_rate(self):
        for rec in self:
            rate = rec.user_accounting_rate
            if rate:
                if rec.accounting_rate_inverted:
                    rec.accounting_rate = 1.0 / rate
                else:
                    rec.accounting_rate = rate

    @api.depends("counterpart_rate", "counterpart_rate_inverted")
    def _compute_user_counterpart_rate(self):
        for rec in self:
            rate = rec.counterpart_rate
            if not rate:
                rec.user_counterpart_rate = 0.0
            elif rec.counterpart_rate_inverted:
                rec.user_counterpart_rate = 1.0 / rate
            else:
                rec.user_counterpart_rate = rate

    @api.onchange("user_counterpart_rate")
    def _inverse_user_counterpart_rate(self):
        for rec in self:
            rate = rec.user_counterpart_rate
            if not rate:
                continue
            if rec.counterpart_rate_inverted:
                rec.counterpart_rate = 1.0 / rate
            else:
                rec.counterpart_rate = rate
            # Propagar a accounting_rate si B1 == C
            if rec.counterpart_currency_id == rec.company_currency_id:
                rec.accounting_rate = rec.counterpart_rate

    @api.depends("to_pay_amount", "accounting_rate")
    def _compute_to_pay_amount_company_currency(self):
        for rec in self:
            if rec.accounting_rate:
                rec.to_pay_amount_company_currency = rec.to_pay_amount / rec.accounting_rate
            else:
                rec.to_pay_amount_company_currency = rec.to_pay_amount

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
                    _("All selected debt lines must have the same currency. " "Found: %s")
                    % ", ".join(currencies.mapped("name"))
                )

    def action_draft(self):
        # Seteamos posted_before en true para que nos permita pasar a borrador el pago y poder realizar cambio sobre el mismo
        # Nos salteamos la siguente validacion
        # https://github.com/odoo/odoo/blob/b6b90636938ae961c339807ea893cabdede9f549/addons/account/models/account_move.py#L2474
        if self.company_id.use_payment_pro:
            self.move_id.posted_before = False
        super().action_draft()

    def write(self, vals):
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
            if rec.counterpart_currency_id and rec.counterpart_currency_id != rec.currency_id:
                if rec.counterpart_rate:
                    # amount está en A, convertir a B1 usando counterpart_rate
                    rec.counterpart_currency_amount = rec.amount * rec.counterpart_rate
                else:
                    rec.counterpart_currency_amount = 0.0
            else:
                # A == B1, son la misma moneda
                rec.counterpart_currency_amount = rec.amount

    def _inverse_counterpart_currency_amount(self):
        for rec in self:
            if rec.counterpart_currency_amount and rec.amount:
                rec.counterpart_rate = rec.counterpart_currency_amount / rec.amount

    @api.depends(
        "accounting_rate", "counterpart_currency_id", "currency_id", "company_currency_id", "company_id", "date"
    )
    def _compute_counterpart_rate(self):
        for rec in self:
            if not rec.counterpart_currency_id:
                rec.counterpart_rate = 1.0
                continue

            # Caso B1 == C: delegar en accounting_rate (misma conversión)
            if rec.counterpart_currency_id == rec.company_currency_id:
                rec.counterpart_rate = rec.accounting_rate
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

    def _inverse_counterpart_rate(self):
        for rec in self:
            if rec.counterpart_currency_id == rec.company_currency_id:
                rec.accounting_rate = rec.counterpart_rate

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self._origin.company_id and self.company_id != self._origin.company_id and self.state == "draft":
            self.remove_all()

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

        liquidity_lines = res.get("liquidity_lines", [])
        counterpart_lines = res.get("counterpart_lines", [])

        if not liquidity_lines or not counterpart_lines:
            return res

        # ── Ajuste de la línea de LIQUIDEZ ────────────────────────────────────────
        # accounting_rate = A/C (formato Odoo nativo, ej: 0.000667 p/USD→ARS)
        # balance_en_C = amount_en_A / accounting_rate
        if self.accounting_rate and self.currency_id != self.company_currency_id:
            liq_amount_currency = liquidity_lines[0]["amount_currency"]
            liquidity_lines[0]["balance"] = liq_amount_currency / self.accounting_rate

        # ── Recalcular balance de CONTRAPARTIDA para cerrar el asiento ────────────
        write_off_balance = sum(line["balance"] for line in res.get("write_off_lines", []))
        withholding_balance = sum(line["balance"] for line in res.get("withholding_lines", []))
        new_liq_balance = liquidity_lines[0]["balance"]
        counterpart_lines[0]["balance"] = -new_liq_balance - write_off_balance - withholding_balance

        # ── Ajuste de MONEDA en la línea de CONTRAPARTIDA ─────────────────────────
        # Si A != B1: la contrapartida va en moneda B1 (counterpart_currency_id)
        if self.counterpart_currency_id and self.counterpart_currency_id != self.currency_id:
            cp_sign = 1 if counterpart_lines[0].get("amount_currency", 0) >= 0 else -1
            counterpart_lines[0].update(
                {
                    "currency_id": self.counterpart_currency_id.id,
                    "amount_currency": cp_sign * abs(self.counterpart_currency_amount),
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

    def _create_paired_internal_transfer_payment(self):
        for rec in self:
            super(
                AccountPayment,
                rec.with_context(default_accounting_rate=rec.accounting_rate),
            )._create_paired_internal_transfer_payment()

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
        "amount",
        "counterpart_currency_amount",
        "write_off_amount",
        "currency_id",
        "destination_currency_id",
        "payment_type",
        "partner_type",
    )
    def _compute_payment_total(self):
        for rec in self:
            if rec.currency_id == rec.destination_currency_id:
                base_amount = rec.amount
            else:
                base_amount = rec.counterpart_currency_amount

            if (
                rec.payment_type == "outbound"
                and rec.partner_type == "customer"
                or rec.payment_type == "inbound"
                and rec.partner_type == "supplier"
            ):
                base_amount = -base_amount

            rec.payment_total = base_amount + rec.write_off_amount

    # TODO revisar depends
    @api.depends("payment_total", "to_pay_amount")
    def _compute_payment_difference(self):
        for rec in self:
            rec.payment_difference = rec.to_pay_amount - rec.payment_total

    # En el pasado se contaba con to_pay_move_line_ids.amount_residual dentro de los depends,  y no deberiamos por cuestiones de performance, ya que ademas no era necesario
    @api.depends("to_pay_move_line_ids", "destination_currency_id")
    def _compute_selected_debt(self):
        for rec in self:
            sign = -1.0 if rec.partner_type == "supplier" else 1.0
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

        with_payment_pro = self._get_filter_payments(records, ["direct_debit_mandate_id"])

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
        return domain

    def _add_all(self):
        for rec in self:
            rec.to_pay_move_line_ids = [
                Command.clear(),
                Command.set(self.env["account.move.line"].search(rec._get_to_pay_move_lines_domain()).ids),
            ]

    def action_add_all(self):
        self.with_context(active_ids=False)._add_all()

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
            # Lo sacamos ya que no es correcto de odoo cuando se deslinkea el pago
            # o se linkea por otro lado el pago no lo suma. Decidimos dejarlo por si surge la necesidad
            # Si surge la necesidad habria que tratar de que lo de odoo nativo funcione
            # if rec.company_id.use_payment_pro:
            #     for invoices in (rec.reconciled_invoice_ids + rec.reconciled_bill_ids):
            #         invoices.matched_payment_ids += rec

    def action_post(self):
        res = super().action_post()
        self._check_to_pay_lines_account()
        self._reconcile_after_post()
        return res

    def _get_mached_payment(self):
        return self.ids

    # --- ORM METHODS--- #
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
    @api.depends()
    def _compute_company_id(self):
        return super()._compute_company_id()

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
