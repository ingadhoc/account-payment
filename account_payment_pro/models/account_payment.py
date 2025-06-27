from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # TODO. por ahora por simplicidad y para mantener lo que teniamos hasta 16 hacemos que todos los campos de deuda y demas
    # sean en moneda de la compañia (antes era en moneda del pay group que siempre era la moneda de la cia), currency_field='company_currency_id',
    # desde account_payment_group, modelo account.payment
    amount_company_currency = fields.Monetary(
        string="Amount on Company Currency",
        compute="_compute_amount_company_currency",
        inverse="_inverse_amount_company_currency",
        currency_field="company_currency_id",
    )
    counterpart_currency_amount = fields.Monetary(
        currency_field="counterpart_currency_id",
        compute="_compute_counterpart_currency_amount",
    )
    counterpart_currency_id = fields.Many2one("res.currency")
    counterpart_exchange_rate = fields.Float(
        readonly=False,
        compute="_compute_counterpart_exchange_rate",
        store=True,
        precompute=True,
        copy=False,
        digits=0,
    )
    other_currency = fields.Boolean(
        compute="_compute_other_currency",
    )
    journal_currency_id = fields.Many2one(related="journal_id.currency_id", string="Journal Currency")
    destination_journal_currency_id = fields.Many2one(
        related="destination_journal_id.currency_id", string="Destination Journal Currency"
    )
    force_amount_company_currency = fields.Monetary(
        string="Forced Amount on Company Currency",
        currency_field="company_currency_id",
        copy=False,
    )
    exchange_rate = fields.Float(
        compute="_compute_exchange_rate",
        # readonly=False,
        # inverse='_inverse_exchange_rate',
        # digits=(16, 4),
    )
    commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    # TODO deberiamos ver de borrar esto. el tema es que los campos nativos de odoo no refelajn importe en moenda de cia
    # hasta en tanto se guarde el payment (en parte porque vienen heredados desde el move)
    # no solo eso si no que tmb viene pisado en los payments y computa solo si hay liquidity lines pero no cuentas de
    # outstanding
    # TODO de hecho tenemos que analizar si queremos mantener todo lo de matched y demas en moneda de cia o moneda de
    # pago
    amount_company_currency_signed_pro = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_amount_company_currency_signed_pro",
    )
    payment_total = fields.Monetary(
        compute="_compute_payment_total", tracking=True, currency_field="company_currency_id"
    )
    available_journal_ids = fields.Many2many(comodel_name="account.journal", compute="_compute_available_journal_ids")
    # desde account_payment_group, modelo account.payment.group
    matched_amount = fields.Monetary(
        compute="_compute_matched_amounts",
        currency_field="company_currency_id",
    )
    unmatched_amount = fields.Monetary(
        compute="_compute_matched_amounts",
        currency_field="company_currency_id",
    )
    selected_debt = fields.Monetary(
        compute="_compute_selected_debt",
        currency_field="company_currency_id",
    )
    unreconciled_amount = fields.Monetary(
        string="Adjustment / Advance",
        currency_field="company_currency_id",
    )
    # reconciled_amount = fields.Monetary(compute='_compute_amounts')
    to_pay_amount = fields.Monetary(
        compute="_compute_to_pay_amount",
        inverse="_inverse_to_pay_amount",
        readonly=True,
        tracking=True,
        currency_field="company_currency_id",
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
        currency_field="company_currency_id",
    )
    payment_difference = fields.Monetary(
        compute="_compute_payment_difference",
        string="Payments Difference",
        currency_field="company_currency_id",
        help="Difference between 'To Pay Amount' and 'Payment Total'",
    )
    write_off_available = fields.Boolean(compute="_compute_write_off_available")
    use_payment_pro = fields.Boolean(compute="_compute_use_payment_pro")

    open_move_line_ids = fields.One2many(related="move_id.open_move_line_ids")

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

    @api.constrains("to_pay_move_line_ids", "state")
    def _check_to_pay_lines_account(self):
        """TODO ver si esto tmb lo llevamos a la UI y lo mostramos como un warning.
        tmb podemos dar mas info al usuario en el error"""
        for rec in self.filtered(lambda x: x.partner_id and x.state != "draft"):
            accounts = rec.to_pay_move_line_ids.mapped("account_id")
            if len(accounts) > 1:
                raise ValidationError(_("To Pay Lines must be of the same account!"))

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

    @api.depends("company_id")
    def _compute_available_journal_ids(self):
        # Cambiamos el metodo para que traiga los journals de la compañia sobre la cual se esta imputando el pago.
        # Le agregamos el onchange de company para asegurarnos de que los available journals se computen siempre
        # que se produce un cambio de compañia
        if self.company_id:
            self.env.company = self.company_id
        super()._compute_available_journal_ids()

    @api.depends("currency_id", "destination_journal_currency_id")
    def _compute_other_currency(self):
        for rec in self:
            rec.other_currency = False
            if rec.company_currency_id and rec.currency_id and rec.company_currency_id != rec.currency_id:
                rec.other_currency = True
            elif (
                rec.is_internal_transfer
                and rec.destination_journal_currency_id
                and rec.company_currency_id != rec.destination_journal_currency_id
            ):
                rec.other_currency = True

    @api.depends("amount", "other_currency", "amount_company_currency")
    def _compute_exchange_rate(self):
        for rec in self:
            if rec.other_currency:
                rec.exchange_rate = rec.amount and (rec.amount_company_currency / rec.amount) or 0.0
            else:
                rec.exchange_rate = False

    @api.depends("payment_total", "counterpart_exchange_rate")
    def _compute_counterpart_currency_amount(self):
        for rec in self:
            if rec.counterpart_currency_id and rec.counterpart_exchange_rate:
                rec.counterpart_currency_amount = rec.payment_total / rec.counterpart_exchange_rate
            else:
                rec.counterpart_currency_amount = False

    @api.depends("counterpart_currency_id", "company_id", "date")
    def _compute_counterpart_exchange_rate(self):
        for rec in self:
            if rec.counterpart_currency_id:
                rate = self.env["res.currency"]._get_conversion_rate(
                    from_currency=rec.company_currency_id,
                    to_currency=rec.counterpart_currency_id,
                    company=rec.company_id,
                    date=rec.date,
                )
                rec.counterpart_exchange_rate = 1 / rate if rate else False
            else:
                rec.counterpart_exchange_rate = False

    # this onchange is necesary because odoo, sometimes, re-compute
    # and overwrites amount_company_currency. That happends due to an issue
    # with rounding of amount field (amount field is not change but due to
    # rouding odoo believes amount has changed)
    @api.onchange("amount_company_currency")
    def _inverse_amount_company_currency(self):
        for rec in self:
            if rec.other_currency and rec.amount_company_currency != rec.currency_id._convert(
                rec.amount, rec.company_id.currency_id, rec.company_id, rec.date
            ):
                force_amount_company_currency = rec.amount_company_currency
            else:
                force_amount_company_currency = False
            rec.force_amount_company_currency = force_amount_company_currency

    @api.depends("amount", "other_currency", "force_amount_company_currency")
    def _compute_amount_company_currency(self):
        """
        * Si las monedas son iguales devuelve 1
        * si no, si hay force_amount_company_currency, devuelve ese valor
        * sino, devuelve el amount convertido a la moneda de la cia
        """
        for rec in self:
            if not rec.other_currency:
                amount_company_currency = rec.amount
            elif rec.force_amount_company_currency:
                amount_company_currency = rec.force_amount_company_currency
            else:
                amount_company_currency = rec.currency_id._convert(
                    rec.amount, rec.company_id.currency_id, rec.company_id, rec.date
                )
            rec.amount_company_currency = amount_company_currency

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

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        # TODO: elimino los write_off_line_vals  porque los regenero tanto aca
        # como en retenciones. esto puede generar problemas
        if not self.company_id.use_payment_pro:
            return super()._prepare_move_line_default_vals(
                write_off_line_vals=write_off_line_vals, force_balance=force_balance
            )
        write_off_line_vals = []
        if self.write_off_amount:
            if self.payment_type == "inbound":
                # Receive money.
                write_off_amount_currency = self.write_off_amount
            else:
                # Send money.
                write_off_amount_currency = -self.write_off_amount

            write_off_line_vals.append(
                {
                    "name": self.write_off_type_id.label or self.write_off_type_id.name,
                    "account_id": self.write_off_type_id.account_id.id,
                    "partner_id": self.partner_id.id,
                    "currency_id": self.currency_id.id,
                    "amount_currency": write_off_amount_currency,
                    "balance": self.currency_id._convert(
                        write_off_amount_currency, self.company_id.currency_id, self.company_id, self.date
                    ),
                }
            )
        res = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance
        )
        if self.force_amount_company_currency:
            difference = self.force_amount_company_currency - res[0]["credit"] - res[0]["debit"]
            if res[0]["credit"]:
                liquidity_field = "credit"
                counterpart_field = "debit"
            else:
                liquidity_field = "debit"
                counterpart_field = "credit"
            res[0].update(
                {
                    liquidity_field: self.force_amount_company_currency,
                }
            )
            res[1].update(
                {
                    counterpart_field: res[1][counterpart_field] + difference,
                }
            )

        if self._use_counterpart_currency():
            if self.payment_type == "inbound":
                # Receive money.
                liquidity_amount_currency = self.counterpart_currency_amount
            elif self.payment_type == "outbound":
                # Send money.
                liquidity_amount_currency = -self.counterpart_currency_amount
            res[1].update(
                {
                    "currency_id": self.counterpart_currency_id.id,
                    "amount_currency": -liquidity_amount_currency,
                }
            )
        return res

    def _use_counterpart_currency(self):
        self.ensure_one()
        return (
            self.counterpart_currency_id
            and self.currency_id == self.company_id.currency_id
            and self.counterpart_currency_id != self.currency_id
        )

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        # si bien es un metodo api.model usamos este hack para chequear si es la creacion de un payment que termina
        # triggereando un write y luego llamando a este metodo y dando error, por ahora no encontramos una mejor forma
        # esto esta ligado de alguna manera a un llamado que se hace dos veces por "culpa" del método
        # "_inverse_amount_company_currency". Si bien no es elegante para todas las pruebas que hicimos funcionó bien.
        if self.mapped("move_id"):
            res = res + ("force_amount_company_currency", "counterpart_exchange_rate", "counterpart_currency_id")
        return res + (
            "write_off_amount",
            "write_off_type_id",
        )

    def _create_paired_internal_transfer_payment(self):
        for rec in self:
            super(
                AccountPayment,
                rec.with_context(default_force_amount_company_currency=rec.force_amount_company_currency),
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

    @api.depends(
        "state",
        "amount_company_currency_signed_pro",
    )
    def _compute_matched_amounts(self):
        for rec in self:
            rec.matched_amount = 0.0
            rec.unmatched_amount = 0.0
            if rec.state == "draft":
                continue
            # damos vuelta signo porque el payments_amount tmb lo da vuelta,
            # en realidad porque siempre es positivo y se define en funcion
            # a si es pago entrante o saliente
            sign = rec.partner_type == "supplier" and -1.0 or 1.0
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

    @api.depends("amount_company_currency_signed_pro", "write_off_amount")
    def _compute_payment_total(self):
        for rec in self:
            rec.payment_total = rec.amount_company_currency_signed_pro + rec.write_off_amount

    @api.depends("amount_company_currency", "payment_type")
    def _compute_amount_company_currency_signed_pro(self):
        """new field similar to amount_company_currency_signed but:
        1. is positive for payments to suppliers
        2. we use the new field amount_company_currency instead of amount_total_signed, because amount_total_signed is
        computed only after saving
        We use l10n_ar prefix because this is a pseudo backport of future l10n_ar_withholding module"""
        for payment in self:
            if (
                payment.payment_type == "outbound"
                and payment.partner_type == "customer"
                or payment.payment_type == "inbound"
                and payment.partner_type == "supplier"
            ):
                payment.amount_company_currency_signed_pro = -payment.amount_company_currency
            else:
                payment.amount_company_currency_signed_pro = payment.amount_company_currency

    # TODO revisar depends
    @api.depends("payment_total", "to_pay_amount", "amount_company_currency_signed_pro")
    def _compute_payment_difference(self):
        for rec in self:
            rec.payment_difference = rec.to_pay_amount - rec.payment_total

    def action_post_and_new(self):
        self.ensure_one()
        self.action_post()
        return self.to_pay_move_line_ids.with_context(
            force_payment_pro=True,
            create_and_new=True,
            default_move_journal_types=("bank", "cash"),
            default_to_pay_amount=self.payment_difference,
            default_l10n_ar_fiscal_position_id=False,
            default_partner_type=self.partner_type,
            default_company_id=self.company_id.id,
            default_partner_id=self.partner_id.id,
        ).action_register_payment()

    # En el pasado se contaba con to_pay_move_line_ids.amount_residual dentro de los depends,  y no deberiamos por cuestiones de performance, ya que ademas no era necesario
    @api.depends("to_pay_move_line_ids")
    def _compute_selected_debt(self):
        for rec in self:
            # factor = 1
            amount_residual = sum(rec.to_pay_move_line_ids._origin.mapped("amount_residual"))
            if self.env.context.get("pay_now") and amount_residual != sum(
                rec.to_pay_move_line_ids._origin.mapped("amount_residual_currency")
            ):
                amount_residual = sum(rec.to_pay_move_line_ids._origin.mapped("amount_residual_currency"))
            rec.selected_debt = amount_residual * (-1.0 if rec.partner_type == "supplier" else 1.0)

            # TODO error en la creacion de un payment desde el menu?
            # if rec.payment_type == 'outbound' and rec.partner_type == 'customer' or \
            #         rec.payment_type == 'inbound' and rec.partner_type == 'supplier':
            #     factor = -1
            # rec.selected_debt = sum(rec.to_pay_move_line_ids._origin.mapped('amount_residual')) * factor

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

    # We dont set 'is_internal_transfer' as a dependencies as it could leed to recompute to_pay_move_line_ids
    @api.depends("partner_id", "partner_type", "company_id")
    def _compute_to_pay_move_lines(self):
        # TODO ?
        # # if payment group is being created from a payment we dont want to compute to_pay_move_lines
        # if self._context.get('created_automatically'):
        #     return

        # Se recomputan las lienas solo si la deuda que esta seleccionada solo si
        # cambio el partner, compania o partner_type
        records = self.filtered(lambda x: x.state == "draft")
        internal_transfers = records.filtered(lambda x: x.is_internal_transfer)

        with_payment_pro = self._get_filter_payments(records, ["direct_debit_mandate_id"])

        if internal_transfers or not self._context.get("pay_now"):
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
        if self.env.context.get("active_ids"):
            domain.append(("move_id.line_ids", "in", self.env.context.get("active_ids")))
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
            debt_aml = rec.to_pay_move_line_ids.filtered(lambda r: not r.reconciled)
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
