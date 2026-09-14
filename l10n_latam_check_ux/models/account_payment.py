from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    l10n_latam_move_check_ids_operation_date = fields.Datetime(
        string="Operation Date",
        default=fields.Datetime.now(),
    )

    @api.constrains("l10n_latam_move_check_ids_operation_date", "state")
    def _check_last_operation_on_state_change(self):
        """
        Constraint to prevent changing the state of a check operation if it is not the last operation.
        """
        import_file = self.env.context.get("import_file")
        if not import_file:
            return
        for rec in self:
            # Only validate if the payment has checks associated and state is changing
            checks = rec.l10n_latam_move_check_ids | rec.l10n_latam_new_check_ids
            for check in checks:
                last_operation = check._get_last_operation()
                if last_operation and rec != last_operation:
                    raise ValidationError(
                        "You cannot change the state of this operation because it is not the last operation for check %s."
                        % check.name
                    )

    def action_post(self):
        # nosotros queremos bloquear tmb nros de cheques de terceros que sea unicos
        # para esto chequeamos el campo computado de warnings que ya lo tiene incorporado
        # NOTA: no mandamos todos los warnings de "self" juntos porque podría ser muy verbose (por ej. la
        # leyenda de cheques duplicados en un mismo payment group apareceria varias veces si el cheque está repetido
        # en el mismo payment group)
        for rec in self:
            if rec.l10n_latam_check_warning_msg:
                raise ValidationError("%s" % rec.l10n_latam_check_warning_msg)
            rec.l10n_latam_move_check_ids_operation_date = rec.create_date if rec.create_date else fields.Datetime.now()

        # Detectar cheques de terceros existentes usados más de una vez dentro del mismo
        # batch de confirmación (ej: bundle confirma dos pagos hijos en draft que tienen
        # el mismo cheque, sin que ninguno lo haya bloqueado antes de postear).
        seen = self.env["l10n_latam.check"]
        for rec in self.filtered("l10n_latam_move_check_ids"):
            repeated = rec.l10n_latam_move_check_ids & seen
            if repeated:
                raise ValidationError(
                    "The same check cannot be confirmed in two payments at the same time: %s"
                    % ", ".join(repeated.mapped("display_name"))
                )
            seen |= rec.l10n_latam_move_check_ids

        super().action_post()

    def _create_paired_internal_transfer_payment(self):
        """
        Two modifications when only when transferring from a third party checks journal:
        1. When a paired transfer is created, the default odoo behavior is to use on the paired transfer the first
        available payment method. If we are transferring to another third party checks journal, then set as payment
        method on the paired transfer 'in_third_party_checks' or 'out_third_party_checks'
        2. On the paired transfer set the l10n_latam_check_id field, this field is needed for the
        l10n_latam_check_operation_ids and also for some warnings and constrains.
        """
        # We evalute if the transfer is creating from de wizard transfer check button with check_deposit_transfer context,
        # in order to not duplicate the transfer when creating the deposit of the check from the wizard.
        # Who already create both payments at once in the _create_payments method.)
        if not self.env.context.get("check_deposit_transfer"):
            third_party_checks = self.filtered(
                lambda x: (
                    x.payment_method_line_id.code
                    in ["in_third_party_checks", "out_third_party_checks", "return_third_party_checks"]
                )
            )
            for rec in third_party_checks:
                dest_payment_method_code = (
                    "in_third_party_checks" if rec.payment_type == "outbound" else "out_third_party_checks"
                )
                dest_payment_method = rec.destination_journal_id.inbound_payment_method_line_ids.filtered(
                    lambda x: x.code == dest_payment_method_code
                )
                if dest_payment_method:
                    super(
                        AccountPayment,
                        rec.with_context(
                            default_payment_method_line_id=dest_payment_method.id,
                            default_l10n_latam_move_check_ids=rec.l10n_latam_move_check_ids,
                        ),
                    )._create_paired_internal_transfer_payment()
                else:
                    super(
                        AccountPayment,
                        rec.with_context(
                            default_l10n_latam_move_check_ids=rec.l10n_latam_move_check_ids,
                        ),
                    )._create_paired_internal_transfer_payment()

                # The outbound must have a greater operation_date than the inbound so it is
                # identified as the latest operation. Subtract 1s from the inbound payment.
                if rec.payment_type == "inbound":
                    rec.write(
                        {
                            "l10n_latam_move_check_ids_operation_date": rec.l10n_latam_move_check_ids_operation_date
                            + timedelta(minutes=1)
                        }
                    )
                else:
                    rec.write(
                        {
                            "l10n_latam_move_check_ids_operation_date": rec.l10n_latam_move_check_ids_operation_date
                            - timedelta(minutes=1)
                        }
                    )
                rec._get_latam_checks()._compute_current_journal()
                rec._get_latam_checks()._compute_company_id()

                # If the journal belongs to the third-party checks journal, posting the move was incorrectly removing the checks,
                # even though the payment method line is for checks.
                # To fix this, we replicate the same behavior as in Odoo's "transfer check" wizard by setting the proper payment method.
                correct_dest_payment_method = rec.destination_journal_id.inbound_payment_method_line_ids.filtered(
                    lambda x: x.code == "in_third_party_checks"
                )
                if correct_dest_payment_method:
                    rec.paired_internal_transfer_payment_id.payment_method_line_id = correct_dest_payment_method
            super(AccountPayment, self - third_party_checks)._create_paired_internal_transfer_payment()

    def _get_reconciled_checks_error(self):
        """No bloquear los cheques propios con débito automático.

        Cuando la cuenta del método de pago de cheques propios no es conciliable (típicamente
        porque es la misma cuenta del diario de liquidez, es decir el banco debita el cheque al
        emitirlo), el cheque nace en ``debited`` y nunca va a salir de ese estado: no hay
        conciliación que lo mueva (ver ``l10n_latam.check._compute_issue_state``). La restricción
        del core existe para no romper la conciliación que debitó o anuló el cheque, así que en
        este caso no aplica y el pago se puede restablecer a borrador o cancelar.
        """
        payments_with_reconciled_checks = self.filtered(
            lambda payment: payment.l10n_latam_new_check_ids.filtered(
                lambda check: check.issue_state in ("debited", "voided")
                and check.outstanding_line_id.account_id.reconcile
            )
        )
        return super(AccountPayment, payments_with_reconciled_checks)._get_reconciled_checks_error()

    def action_draft(self):
        for rec in self:
            for check in rec.mapped("l10n_latam_move_check_ids") + rec.mapped("l10n_latam_new_check_ids"):
                last_operation = check._get_last_operation()
                if rec != last_operation:
                    raise ValidationError(
                        "You cannot reset this operation to draft because it is not the last operation for the checks."
                    )

        super().action_draft()

    def _is_latam_check_transfer(self):
        self.ensure_one()
        return super()._is_latam_check_transfer() or (
            self.is_internal_transfer
            and bool(self.l10n_latam_move_check_ids)
            and self.destination_account_id == self.company_id.transfer_account_id
        )

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_clear_move_checks(self):
        """When destination journal changes on an inbound internal transfer, remove checks
        that are no longer in the (new) destination journal."""
        for rec in self.filtered(
            lambda x: (
                x.is_internal_transfer
                and x.payment_type == "inbound"
                and x.payment_method_code == "in_third_party_checks"
                and x.l10n_latam_move_check_ids
            )
        ):
            invalid = rec.l10n_latam_move_check_ids.filtered(
                lambda c: c.current_journal_id != rec.destination_journal_id
            )
            if invalid:
                rec.l10n_latam_move_check_ids -= invalid

    @api.constrains(
        "is_internal_transfer",
        "payment_type",
        "payment_method_line_id",
        "destination_journal_id",
        "l10n_latam_move_check_ids",
    )
    def _check_inbound_transfer_checks_current_journal(self):
        """Keep server-side behavior aligned with the wizard domain in Odoo.

        For inbound internal transfers receiving third-party checks, all selected checks
        must come from the same current journal: the source journal (`destination_journal_id`).
        """
        for rec in self.filtered(
            lambda x: (
                x.state == "draft"
                and x.is_internal_transfer
                and x.payment_type == "inbound"
                and x.payment_method_line_id.code == "in_third_party_checks"
                and x.destination_journal_id
                and x.l10n_latam_move_check_ids
            )
        ):
            invalid_checks = rec.l10n_latam_move_check_ids.filtered(
                lambda c: c.current_journal_id and c.current_journal_id != rec.destination_journal_id
            )
            if invalid_checks:
                raise ValidationError(
                    "All selected checks must belong to the source journal (%s)."
                    % rec.destination_journal_id.display_name
                )

    def _l10n_latam_check_liquidity_lines(self):
        """Una línea de liquidez por cheque, con su nominal, su vencimiento y su link (tarea 70884).

        Relocaliza lo que hace `l10n_latam_check` cuando la imagen mergea el PR odoo#248741, para
        que el asiento salga igual con un core sin parchear. El balance queda a la cotización del
        pago; la revaluación de abajo lo ajusta a la del asiento.
        """
        check_suffix = "".join([item[1] for item in self._get_aml_default_display_name_list()])
        line_common_vals = {
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "account_id": self.outstanding_account_id.id,
        }
        liquidity_vals = []
        for check in self.l10n_latam_new_check_ids | self.l10n_latam_move_check_ids:
            liquidity_amount = check.amount if self.payment_type == "inbound" else -check.amount
            liquidity_vals.append(
                {
                    "name": _("Check %(check_number)s - %(suffix)s", check_number=check.name, suffix=check_suffix),
                    "date_maturity": check.payment_date,
                    "amount_currency": liquidity_amount,
                    "balance": self.currency_id._convert(
                        liquidity_amount, self.company_currency_id, self.company_id, self.date
                    ),
                    "l10n_latam_check_ids": [Command.set(check.ids)],
                    **line_common_vals,
                }
            )
        return liquidity_vals

    def _l10n_latam_check_split_move(self):
        """No-op: las líneas de liquidez de arriba reemplazan al split move."""
        return

    def _l10n_latam_check_unlink_split_move(self):
        """Solo desarma el split move de los pagos posteados antes de este cambio: si no queda
        posteado y huérfano, con el importe del cheque en la cuenta outstanding."""
        self.ensure_one()
        for check in self.l10n_latam_new_check_ids:
            if not check.outstanding_line_id or self.move_id == check.outstanding_line_id.move_id:
                continue
            check.outstanding_line_id.move_id.button_draft()
            check.outstanding_line_id.move_id.unlink()

    def _synchronize_to_moves(self, changed_fields):
        """Base bloquea escribir ``amount`` cuando el asiento tiene más de una línea de liquidez, y
        los pagos con cheques tienen una por cheque: se saca del set y el mapeo lo sigue haciendo
        base. Si ``amount`` es el único campo escrito no se re-sincroniza nada, inocuo porque se
        recalcula desde los cheques."""
        with_checks = self.filtered(lambda x: x.l10n_latam_new_check_ids or x.l10n_latam_move_check_ids)
        super(AccountPayment, self - with_checks)._synchronize_to_moves(changed_fields)
        if with_checks:
            super(AccountPayment, with_checks)._synchronize_to_moves(
                tuple(field for field in changed_fields if field != "amount")
            )

    def _prepare_paired_payment_values(self):
        """Override to validate check payment method combinations on internal transfers.

        Rules:
        - Third-party check outbounds must pair with third-party check inbounds
        - Non-check payment methods cannot pair with check methods (except the above)
        - Check outbound methods cannot be paired destinations
        """
        vals = super()._prepare_paired_payment_values()
        if not self.is_internal_transfer:
            return vals

        paired_method_code = (
            self.env["account.payment.method.line"].browse(vals.get("payment_method_line_id")).code
            if vals.get("payment_method_line_id")
            else None
        )
        source_method_code = self.payment_method_line_id.code

        # Valid check method codes
        check_inbound_codes = {"in_third_party_checks", "new_third_party_checks"}
        check_outbound_codes = {"out_third_party_checks", "return_third_party_checks", "own_checks"}
        all_check_codes = check_inbound_codes | check_outbound_codes

        # Rule 1: Outbound third-party checks must pair with inbound third-party checks
        if source_method_code == "out_third_party_checks":
            if paired_method_code not in ["in_third_party_checks", "manual", "new_third_party_checks"]:
                raise ValidationError(
                    "When transferring third-party checks out (source: '%s'), "
                    "the destination journal must have the 'Third Party Checks' inbound method. "
                    "Please select a different destination journal." % self.payment_method_line_id.name
                )

        # Rule 2: Non-third-party-check outbounds cannot pair with any check method
        elif (
            source_method_code not in ["out_third_party_checks", "return_third_party_checks"]
            and paired_method_code in all_check_codes
        ):
            raise ValidationError(
                "The payment method '%s' cannot be paired with a check payment method. "
                "To transfer checks, use a third-party checks journal as the source. "
                "Please select a different destination journal."
                % (
                    self.env["account.payment.method.line"].browse(vals.get("payment_method_line_id")).name
                    if vals.get("payment_method_line_id")
                    else "None"
                )
            )

        # Rule 3: Check outbound methods cannot be on the paired (destination) side
        # (This catches edge cases where config might slip through)
        if paired_method_code in check_outbound_codes:
            raise ValidationError(
                "Outbound check methods (%s) are not allowed on the destination journal. "
                "Please configure the destination journal with appropriate inbound payment methods."
                % (
                    self.env["account.payment.method.line"].browse(vals.get("payment_method_line_id")).name
                    if vals.get("payment_method_line_id")
                    else "None"
                )
            )

        return vals

    @api.depends("l10n_latam_new_check_ids.amount", "l10n_latam_move_check_ids.amount")
    def _compute_counterpart_currency_amount(self):
        """Con varios cheques, el importe mostrado se arma como el del asiento: cheque por cheque.

        El campo es de `account_payment_pro` y convierte el total de una sola vez; el asiento redondea
        cada línea de cheque por separado y suma. Esa diferencia se veía como un centavo entre el
        importe del pago y su propia línea contable (ticket 123832). Se usa la misma cotización que el
        asiento —la que sale de `amount_exact`, no la del campo— porque si no vuelve a diferir justo
        en los flujos donde el usuario tipea el importe.

        El resto de los pagos ni pasa por acá.
        """
        per_check = self.filtered(lambda pay: pay._has_counterpart_amount_per_check())
        super(AccountPayment, self - per_check)._compute_counterpart_currency_amount()
        for pay in per_check:
            rate = (pay.amount_exact or pay.amount) / pay.accounting_rate / pay.amount
            pay.counterpart_currency_amount = sum(
                pay.company_currency_id.round(check.amount * rate)
                for check in pay.l10n_latam_new_check_ids | pay.l10n_latam_move_check_ids
            )

    def _inverse_counterpart_currency_amount(self):
        """El reparto por cheque no es un importe tipeado por el usuario.

        El inverse de `account_payment_pro` deduce el importe del pago del que muestra la
        contrapartida, y así recupera precisión cuando el importe llega de una sincronización (tarea
        65829). Pero con varios cheques la diferencia es el resto de repartir, no un importe nuevo:
        aplicarlo correría el `amount` del pago y los cheques dejarían de sumarlo (ticket 123832).
        """
        for pay in self:
            if pay._has_counterpart_amount_per_check():
                continue
            super(AccountPayment, pay)._inverse_counterpart_currency_amount()

    def _has_counterpart_amount_per_check(self):
        """Si el importe de la contrapartida lo arma el reparto cheque por cheque."""
        self.ensure_one()
        return bool(
            self.counterpart_currency_id == self.company_currency_id
            and self.accounting_rate
            and self.amount
            and len(self.l10n_latam_new_check_ids | self.l10n_latam_move_check_ids) > 1
        )

    def _prepare_move_liquidity_lines(self, default_values):
        """Valúa todos los cheques a la cotización que el asiento ya dio por buena.

        `l10n_latam_check` convierte cada cheque a la cotización de su propia fecha de vencimiento y
        descarta el balance que recibe acá, que es el que la contrapartida ya usó — la cotización del
        pago, o la que llegó como `force_balance`. Con dos cotizaciones en el mismo asiento no cierra:
        "El asiento no está balanceado" al confirmar (ticket 123832, BUG-2 de la task 70884).

        La cotización se deduce de `balance` sobre el importe del pago, NO del par
        balance/amount_currency: con retenciones ese par llega neteado, y en `amount_currency` el core
        le resta importes que pueden venir en otra moneda. Del balance, en cambio, la retención se
        recupera sumándola de vuelta: es una cifra en moneda de compañía y no mezcla nada.

        Se deduce en vez de llamar a `_convert` por línea justamente para honrar el balance que llegó,
        venga de la fecha del pago o forzado, y para no pagar una consulta de cotización por cheque.

        El origen está en `l10n_latam_check._prepare_move_liquidity_lines`, que NO es código de
        odoo/odoo 19.0: llega por el PR odoo#248741 (abierto, de Adhoc) que nuestra imagen mergea.
        El arreglo definitivo va ahí; mientras ese PR siga abierto, esto lo cubre desde afuera. Ojo al
        limpiarlo: el día que el origen respete el balance que entrega, esto queda inocuo pero sigue
        decidiendo dónde cae el resto del redondeo, así que no es un borrado a ciegas.
        """
        lines = super()._prepare_move_liquidity_lines(default_values)
        if not lines[0].get("l10n_latam_check_ids") and (
            self.l10n_latam_new_check_ids | self.l10n_latam_move_check_ids
        ):
            # core sin parchear: las armamos nosotros (tarea 70884)
            lines = self._l10n_latam_check_liquidity_lines()
        if not lines[0].get("l10n_latam_check_ids") or not self.amount:
            # no hay una línea por cheque que revaluar
            return lines

        balance = default_values["balance"]
        if not self.currency_id.is_zero(abs(default_values["amount_currency"]) - abs(self.amount)):
            # el importe llegó neteado: el core ya le restó las retenciones al balance
            # (`liquidity_balance -= withholding_balance`), así que se las devolvemos para
            # recuperar la cotización con la que se armó el asiento.
            balance += sum(line["balance"] for line in self._prepare_move_withholding_lines({}))

        rate = abs(balance) / abs(self.amount)
        for line in lines:
            line["balance"] = self.company_currency_id.round(line["amount_currency"] * rate)
        return lines

    def _prepare_move_lines_per_type(self, write_off_line_vals=None, force_balance=None):
        """La contrapartida se arma desde las líneas que quedaron en el asiento.

        El core la calcula desde un único balance de liquidez, que con cheques no existe: son N
        líneas, cada una redondeada por su cuenta, y con retenciones ese balance además llega neteado
        mientras los cheques van por su importe completo. Sumar lo que realmente quedó —cheques,
        write-off y retenciones— es lo único que cierra en los dos casos.

        `account_payment_pro` hace esta misma cuenta detrás de `use_payment_pro`: si la fórmula
        cambia, hay que cambiarla en los dos lados hasta que viva en `account_ux`.
        """
        res = super()._prepare_move_lines_per_type(write_off_line_vals=write_off_line_vals, force_balance=force_balance)
        liquidity_lines = res["liquidity_lines"]
        if not liquidity_lines[0].get("l10n_latam_check_ids"):
            return res
        counterpart_lines = res["counterpart_lines"]
        if not counterpart_lines:
            return res

        counterpart_lines[0]["balance"] = -sum(
            line["balance"] for key in ("liquidity_lines", "write_off_lines", "withholding_lines") for line in res[key]
        )
        if counterpart_lines[0].get("currency_id") == self.company_currency_id.id:
            # La contrapartida quedó en moneda de compañía: ahí nominal y balance son la misma
            # cifra, y el nominal lo dejó quien calculó el balance anterior. Sin espejarlo, el ORM
            # redondea el nominal viejo, deriva el balance de él y el asiento vuelve a no cerrar.
            counterpart_lines[0]["amount_currency"] = counterpart_lines[0]["balance"]
        return res
