from odoo import models


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = "l10n_latam.payment.mass.transfer"

    def _create_payments(self):
        # Ensure that third-party check deposits made through the Odoo wizard
        # behave the same way as an internal transfer.
        outbound_payment = super(
            L10nLatamPaymentMassTransfer,
            self.with_context(
                is_internal_transfer_menu=True,
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
