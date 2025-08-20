from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = "l10n_latam.payment.mass.transfer"

    main_company_id = fields.Many2one(
        "res.company",
        compute="_compute_main_company",
    )
    destination_journal_id = fields.Many2one(
        check_company=False,
        domain="[('type', 'in', ('bank', 'cash')), ('id', '!=', journal_id), ('company_id', 'child_of', main_company_id)]",
    )
    check_ids = fields.Many2many(
        check_company=False,
    )
    split_payment = fields.Boolean(
        help="If this option is selected, each check will be registered as an individual payment instead of being grouped into a single payment."
    )

    @api.depends("company_id")
    def _compute_main_company(self):
        for rec in self:
            rec.main_company_id = rec.company_id.parent_id or rec.company_id

    def _create_payments(self):
        if self.destination_journal_id.company_id != self.journal_id.company_id:
            raise ValidationError(
                _("In order to transfer checks between branches you need to use internal transfer menu.")
            )
        if self.split_payment:
            return self._create_split_payments()

        # Ensure that third-party check deposits made through the Odoo wizard
        # behave the same way as an internal transfer.
        outbound_payment = super(
            L10nLatamPaymentMassTransfer,
            self.with_context(
                default_is_internal_transfer=True,
                check_deposit_transfer=True,
            ),
        )._create_payments()

        # Retrieve the corresponding inbound payment by finding the reconciled move lines
        # and filtering out the outbound payment's move.
        inbound_payment = (
            outbound_payment.move_id.line_ids.full_reconcile_id.reconciled_line_ids.mapped("move_id")
            .filtered(lambda x: x.id != outbound_payment.move_id.id)
            .mapped("payment_ids")
        )
        inbound_payment.l10n_latam_move_check_ids_operation_date = (
            outbound_payment.l10n_latam_move_check_ids_operation_date + timedelta(seconds=1)
        )

        # Set the paired internal transfer payment IDs to establish the link
        # between the outbound and inbound payments.
        outbound_payment.paired_internal_transfer_payment_id = inbound_payment.id
        outbound_payment.destination_journal_id = self.destination_journal_id
        inbound_payment.paired_internal_transfer_payment_id = outbound_payment.id
        inbound_payment.destination_journal_id = self.journal_id

        return outbound_payment

    def _create_split_payments(self):
        """This is nedeed because we would like to create a payment of type internal transfer for each check with the
        counterpart journal and then, when posting a second payment will be created automatically"""
        self.ensure_one()
        checks = self.check_ids.filtered(
            lambda x: x.payment_method_line_id.code == "new_third_party_checks"
            and x.currency_id == self.check_ids[0].currency_id
        )
        currency_id = self.check_ids[0].currency_id

        pay_method_line = self.journal_id._get_available_payment_method_lines("outbound").filtered(
            lambda x: x.code in ("out_third_party_checks", "return_third_party_checks")
        )[:1]
        outbound_payments = self.env["account.payment"]
        for check in checks:
            outbound_payment = (
                self.env["account.payment"]
                .with_context(check_deposit_transfer=True)
                .create(
                    {
                        "date": self.payment_date,
                        "amount": check.amount,
                        "partner_id": self.env.company.partner_id.id,
                        "payment_type": "outbound",
                        "memo": self.communication,
                        "journal_id": self.journal_id.id,
                        "currency_id": currency_id.id,
                        "is_internal_transfer": True,
                        "payment_method_line_id": pay_method_line.id if pay_method_line else False,
                        "destination_journal_id": self.destination_journal_id.id,
                        "l10n_latam_move_check_ids": [Command.link(check.id)],
                    }
                )
            )
            outbound_payment.action_post()
            inbound_payment = (
                self.env["account.payment"]
                .with_context(check_deposit_transfer=True)
                .create(
                    {
                        "date": self.payment_date,
                        "amount": check.amount,
                        "partner_id": self.env.company.partner_id.id,
                        "payment_type": "inbound",
                        "memo": self.communication,
                        "journal_id": self.destination_journal_id.id,
                        "currency_id": currency_id.id,
                        "is_internal_transfer": True,
                        "destination_journal_id": self.journal_id.id,
                        "paired_internal_transfer_payment_id": outbound_payment.id,
                        "l10n_latam_move_check_ids": [Command.link(check.id)],
                    }
                )
            )

            dest_payment_method = self.destination_journal_id.inbound_payment_method_line_ids.filtered(
                lambda x: x.code == "in_third_party_checks"
            )
            outbound_payment.paired_internal_transfer_payment_id = inbound_payment.id
            if dest_payment_method:
                inbound_payment.payment_method_line_id = dest_payment_method
                inbound_payment.action_post()
            else:
                # In case the journal is not part of the third party check, when posting the move we remove the checks
                # when the payment method line is not for checks, but in this case, we don't want to remove it so that
                # the operation_ids is filled with the two payments
                inbound_payment.with_context(l10n_ar_skip_remove_check=True).action_post()

            inbound_payment.write(
                {
                    "l10n_latam_move_check_ids_operation_date": inbound_payment.l10n_latam_move_check_ids_operation_date
                    + timedelta(seconds=1)
                }
            )
            body_inbound = _("This payment has been created from: ") + outbound_payment._get_html_link()
            inbound_payment.message_post(body=body_inbound)
            body_outbound = _("A second payment has been created: ") + inbound_payment._get_html_link()
            outbound_payment.message_post(body=body_outbound)

            (outbound_payment.move_id.line_ids + inbound_payment.move_id.line_ids).filtered(
                lambda l: l.account_id == outbound_payment.destination_account_id and not l.reconciled
            ).reconcile()

            outbound_payments |= outbound_payment
        return outbound_payments

    @api.constrains("check_ids")
    def _check_company_matches_active_company(self):
        for wizard in self:
            if not wizard.check_ids:
                continue
            company = wizard.check_ids.mapped("company_id")
            if len(company) > 1:
                raise ValidationError(_("All selected checks must belong to the same company."))
            if company.id != self.env.company.id:
                raise ValidationError(
                    _(
                        "Operation not allowed: To transfer the checks, you must be operating in the same company "
                        "where the checks are registered. Please switch to the appropriate company and try again."
                    )
                )
