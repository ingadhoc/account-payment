from odoo import _, api, models
from odoo.exceptions import ValidationError


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = "l10n_latam.payment.mass.transfer"

    def _create_payments(self):
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

        # Set the paired internal transfer payment IDs to establish the link
        # between the outbound and inbound payments.
        outbound_payment.paired_internal_transfer_payment_id = inbound_payment.id
        outbound_payment.destination_journal_id = self.destination_journal_id
        inbound_payment.paired_internal_transfer_payment_id = outbound_payment.id
        inbound_payment.destination_journal_id = self.journal_id

        return outbound_payment

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
