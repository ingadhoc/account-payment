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
            rec.l10n_latam_move_check_ids_operation_date = fields.Datetime.now()
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
                lambda x: x.payment_method_line_id.code
                in ["in_third_party_checks", "out_third_party_checks", "return_third_party_checks"]
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

                rec.write(
                    {
                        "l10n_latam_move_check_ids_operation_date": rec.l10n_latam_move_check_ids_operation_date
                        - timedelta(seconds=1)
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
                lambda c: c.current_journal_id != rec.destination_journal_id
            )
            if invalid_checks:
                raise ValidationError(
                    "All selected checks must belong to the source journal (%s)."
                    % rec.destination_journal_id.display_name
                )

    # One liquidity line per own check (replaces core's post-hoc split move).
    def _prepare_move_liquidity_lines(self, default_values):
        self.ensure_one()
        check_ids = self.l10n_latam_new_check_ids | self.l10n_latam_move_check_ids
        if (
            self.payment_method_code == "own_checks"
            and self.payment_type == "outbound"
            and len(self.l10n_latam_new_check_ids) >= 1
            and check_ids
        ):
            company_currency = self.company_id.currency_id
            amount_currency_total = 0.0
            balance_total = 0.0
            line_vals = []
            for check in check_ids:
                if check == self.l10n_latam_new_check_ids[-1]:
                    # last check absorbs rounding
                    liquidity_amount_currency = self.currency_id.round(
                        abs(default_values["amount_currency"]) - amount_currency_total
                    )
                    liquidity_balance = company_currency.round(abs(default_values["balance"]) - balance_total)
                else:
                    # check.amount is in the payment currency
                    liquidity_amount_currency = self.currency_id.round(check.amount)
                    liquidity_balance = self.currency_id._convert(
                        liquidity_amount_currency, company_currency, self.company_id, self.date
                    )
                    amount_currency_total += liquidity_amount_currency
                    balance_total += liquidity_balance

                line_vals.append(
                    {
                        "name": _(
                            "Check %(check_number)s - %(suffix)s",
                            check_number=check.name,
                            suffix="".join([item[1] for item in self._get_aml_default_display_name_list()]),
                        ),
                        "date_maturity": check.payment_date,
                        "partner_id": self.partner_id.id,
                        "account_id": self.outstanding_account_id.id,
                        "currency_id": check.currency_id.id,
                        "balance": -liquidity_balance,
                        "amount_currency": -liquidity_amount_currency,
                        "l10n_latam_check_ids": [Command.link(check.id)],
                    }
                )
            return line_vals

        return super()._prepare_move_liquidity_lines(default_values)

    # Split move no longer used: liquidity lines are built per check above.
    def _l10n_latam_check_split_move(self):
        return

    # No split move to unlink on draft: own-check liquidity lines live in the
    # payment move itself, so keep the checks linked (matches patched core).
    def _l10n_latam_check_unlink_split_move(self):
        return

    def _synchronize_to_moves(self, changed_fields):
        # Own checks legitimately post several liquidity lines (one per check).
        # Base only blocks them through the "amount + multiple liquidity lines"
        # guard; its line mapping already handles N liquidity lines. So we just
        # drop 'amount' from the trigger set for those payments and let base do
        # the actual sync (no copied mapping -> upstream changes are inherited).
        own_multi = self.filtered(
            lambda p: p.payment_method_code == "own_checks"
            and p.payment_type == "outbound"
            and len(p.l10n_latam_new_check_ids) > 1
        )
        super(AccountPayment, self - own_multi)._synchronize_to_moves(changed_fields)
        if own_multi:
            super(AccountPayment, own_multi)._synchronize_to_moves(tuple(f for f in changed_fields if f != "amount"))
