from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = "l10n_latam.payment.mass.transfer"

    split_payment = fields.Boolean(
        help="If this option is selected, each check will be registered as an individual payment instead of being grouped into a single payment."
    )
    destination_payment_method_line_id = fields.Many2one(
        comodel_name="account.payment.method.line",
        string="Destination Journal Payment Method",
        compute="_compute_destination_payment_method_line_id",
        store=True,
        readonly=False,
        # the destination journal may belong to another branch
        check_company=False,
        help="Payment method line used on the inbound payment created in the destination journal. "
        "It determines the outstanding account of that payment.",
    )
    available_destination_payment_method_line_ids = fields.Many2many(
        comodel_name="account.payment.method.line",
        compute="_compute_available_destination_payment_method_line_ids",
    )

    @api.depends("to_journal_id")
    def _compute_available_destination_payment_method_line_ids(self):
        for wizard in self:
            journal = wizard.to_journal_id
            wizard.available_destination_payment_method_line_ids = (
                journal._get_check_transfer_destination_lines() if journal else False
            )

    @api.depends("available_destination_payment_method_line_ids")
    def _compute_destination_payment_method_line_id(self):
        for wizard in self:
            available_lines = wizard.available_destination_payment_method_line_ids
            # an explicit choice is kept as long as it is still available on the destination journal
            if wizard.destination_payment_method_line_id in available_lines:
                continue
            wizard.destination_payment_method_line_id = available_lines[:1]

    @api.constrains("destination_payment_method_line_id", "to_journal_id")
    def _check_destination_payment_method_line_id(self):
        for wizard in self.filtered("destination_payment_method_line_id"):
            if wizard.destination_payment_method_line_id not in wizard.available_destination_payment_method_line_ids:
                raise ValidationError(
                    _(
                        "The destination payment method %(method)s cannot receive checks on the destination journal %(journal)s.",
                        method=wizard.destination_payment_method_line_id.name,
                        journal=wizard.to_journal_id.name,
                    )
                )

    def _create_payments(self):
        self._check_transfer_companies()

        company = self.check_ids.mapped("company_id")

        if self.split_payment:
            return self.with_company(company)._create_split_payments()

        return self.with_company(company)._create_grouped_payment()

    def _check_transfer_companies(self):
        """Same check as the core, plus the companies must share the VAT: checks only move between branches."""
        self.ensure_one()
        from_company = self.from_journal_id.company_id
        to_company = self.to_journal_id.company_id
        if from_company == to_company:
            return
        if from_company.transfer_account_id != to_company.transfer_account_id:
            raise UserError(
                _(
                    'The Inter-Banks Transfer Account of "%(source_company)s" and "%(destination_company)s" must be the '
                    "same to transfer checks between them.",
                    source_company=from_company.display_name,
                    destination_company=to_company.display_name,
                )
            )
        if from_company.vat != to_company.vat:
            raise ValidationError(
                _(
                    'Checks can only be transferred between companies with the same VAT: "%(source_company)s" and '
                    '"%(destination_company)s" have different VAT numbers.',
                    source_company=from_company.display_name,
                    destination_company=to_company.display_name,
                )
            )

    def _create_grouped_payment(self):
        """Grouped check deposit, registered as an internal transfer.

        Odoo's method forces 'in_third_party_checks' on the inbound payment and posts it in the
        same block, so the payment method line chosen by the user cannot be honoured by extending
        it. The whole flow is built here instead, mirroring what _create_split_payments does.
        """
        self.ensure_one()
        checks = self.check_ids.filtered(
            lambda x: (
                x.payment_method_line_id.code == "new_third_party_checks"
                and x.currency_id == self.check_ids[0].currency_id
            )
        )
        currency_id = self.check_ids[0].currency_id
        amount = sum(checks.mapped("amount"))
        # check_deposit_transfer keeps action_post from creating a third payment for the transfer
        payment_model = self.env["account.payment"].with_context(check_deposit_transfer=True)

        pay_method_line = self.from_journal_id._get_available_payment_method_lines("outbound").filtered(
            lambda x: x.code in ("out_third_party_checks", "return_third_party_checks")
        )[:1]

        outbound_payment = payment_model.create(
            {
                "date": self.payment_date,
                "amount": amount,
                "partner_id": self.from_journal_id.company_id.partner_id.id,
                "payment_type": "outbound",
                "memo": self.communication,
                "journal_id": self.from_journal_id.id,
                "currency_id": currency_id.id,
                "is_internal_transfer": True,
                "payment_method_line_id": pay_method_line.id if pay_method_line else False,
                "destination_journal_id": self.to_journal_id.id,
                "destination_company_id": self.to_journal_id.company_id.id,
                "l10n_latam_move_check_ids": [Command.link(x.id) for x in checks],
            }
        )
        outbound_payment.action_post()

        dest_payment_method = self.destination_payment_method_line_id
        inbound_payment = payment_model.create(
            {
                "date": self.payment_date,
                "amount": amount,
                "partner_id": self.to_journal_id.company_id.partner_id.id,
                "payment_type": "inbound",
                "memo": self.communication,
                "journal_id": self.to_journal_id.id,
                "currency_id": currency_id.id,
                "is_internal_transfer": True,
                "payment_method_line_id": dest_payment_method.id,
                "destination_journal_id": self.from_journal_id.id,
                "destination_company_id": self.from_journal_id.company_id.id,
                "paired_internal_transfer_payment_id": outbound_payment.id,
                "l10n_latam_move_check_ids": [Command.link(x.id) for x in checks],
            }
        )

        inbound_payment.action_post()

        outbound_payment.paired_internal_transfer_payment_id = inbound_payment.id

        body_inbound = _("This payment has been created from: ") + outbound_payment._get_html_link()
        inbound_payment.message_post(body=body_inbound)
        body_outbound = _("A second payment has been created: ") + inbound_payment._get_html_link()
        outbound_payment.message_post(body=body_outbound)

        (outbound_payment.move_id.line_ids + inbound_payment.move_id.line_ids).filtered(
            lambda l: l.account_id == outbound_payment.destination_account_id and not l.reconciled
        ).reconcile()

        return outbound_payment

    def _create_split_payments(self):
        """This is nedeed because we would like to create a payment of type internal transfer for each check with the
        counterpart journal and then, when posting a second payment will be created automatically"""
        self.ensure_one()
        checks = self.check_ids.filtered(
            lambda x: (
                x.payment_method_line_id.code == "new_third_party_checks"
                and x.currency_id == self.check_ids[0].currency_id
            )
        )
        currency_id = self.check_ids[0].currency_id

        pay_method_line = self.from_journal_id._get_available_payment_method_lines("outbound").filtered(
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
                        "partner_id": self.from_journal_id.company_id.partner_id.id,
                        "payment_type": "outbound",
                        "memo": self.communication,
                        "journal_id": self.from_journal_id.id,
                        "currency_id": currency_id.id,
                        "is_internal_transfer": True,
                        "payment_method_line_id": pay_method_line.id if pay_method_line else False,
                        "destination_journal_id": self.to_journal_id.id,
                        "destination_company_id": self.to_journal_id.company_id.id,
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
                        "partner_id": self.to_journal_id.company_id.partner_id.id,
                        "payment_type": "inbound",
                        "memo": self.communication,
                        "journal_id": self.to_journal_id.id,
                        "currency_id": currency_id.id,
                        "is_internal_transfer": True,
                        "destination_journal_id": self.from_journal_id.id,
                        "destination_company_id": self.from_journal_id.company_id.id,
                        "paired_internal_transfer_payment_id": outbound_payment.id,
                        "l10n_latam_move_check_ids": [Command.link(check.id)],
                    }
                )
            )

            dest_payment_method = self.destination_payment_method_line_id
            outbound_payment.paired_internal_transfer_payment_id = inbound_payment.id
            if dest_payment_method:
                inbound_payment.payment_method_line_id = dest_payment_method

            inbound_payment.action_post()

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
