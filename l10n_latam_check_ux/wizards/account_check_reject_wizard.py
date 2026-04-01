##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountCheckRejectWizard(models.TransientModel):
    _name = "account.check.reject.wizard"
    _description = "Reject Third Party Check Wizard"

    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    rejected_journal_id = fields.Many2one(
        "account.journal",
        string="Rejected Checks Journal",
        required=True,
        domain=[("type", "in", ("bank", "cash"))],
        help="Journal used for rejected third-party checks (e.g. 'Cheques de Terceros Rechazados').",
    )
    case_description = fields.Char(
        compute="_compute_case_description",
        string="Action Summary",
    )

    @api.depends("rejected_journal_id")
    def _compute_case_description(self):
        for rec in self:
            checks = rec._get_checks()
            if not checks:
                rec.case_description = False
                continue
            endorsed = checks.filtered(lambda c: rec._get_case_type(c) == "endorsed")
            deposited = checks.filtered(lambda c: rec._get_case_type(c) == "deposited")
            parts = []
            if endorsed:
                parts.append(
                    _("%d endorsed check(s): supplier receipt + customer debit will be created.") % len(endorsed)
                )
            if deposited:
                parts.append(
                    _("%d deposited check(s): bank outgoing transfer + customer debit will be created.")
                    % len(deposited)
                )
            rec.case_description = "  ".join(parts) if parts else False

    def _get_checks(self):
        return self.env["l10n_latam.check"].browse(self._context.get("active_ids", []))

    def _get_case_type(self, check):
        """Return 'endorsed' if the check was given to a supplier, 'deposited' if it is in a bank journal."""
        if check.current_journal_id and check.current_journal_id != check.original_journal_id:
            return "deposited"
        return "endorsed"

    def action_confirm(self):
        checks = self._get_checks()
        if not checks:
            raise UserError(_("No checks selected."))

        for check in checks:
            if check.payment_method_code != "new_third_party_checks":
                raise UserError(
                    _("Check '%s' is not a third-party check and cannot be rejected with this wizard.") % check.name
                )
            self._reject_check(check)

    def _reject_check(self, check):
        case_type = self._get_case_type(check)
        created_payments = self.env["account.payment"]

        if case_type == "endorsed":
            recovery_payment = self._create_endorsed_recovery_payment(check)
            recovery_payment.action_post()
            created_payments |= recovery_payment
        else:
            bank_payment = self._create_bank_transfer_payment(check)
            bank_payment.action_post()
            paired = bank_payment.paired_internal_transfer_payment_id
            created_payments |= bank_payment
            if paired:
                created_payments |= paired

        customer_payment = self._create_customer_return_payment(check)
        customer_payment.action_post()

        # Ensure customer debit is the last operation by giving it a later operation date
        operation_dates = created_payments.filtered(lambda p: p.l10n_latam_move_check_ids_operation_date).mapped(
            "l10n_latam_move_check_ids_operation_date"
        )
        if operation_dates:
            customer_payment.l10n_latam_move_check_ids_operation_date = max(operation_dates) - timedelta(seconds=1)

    def _create_endorsed_recovery_payment(self, check):
        """Case A: Create inbound payment in rejected_journal to recover the check from the endorsee (vendor)."""
        inbound_method = self.rejected_journal_id._get_available_payment_method_lines("inbound").filtered(
            lambda x: x.code == "in_third_party_checks"
        )[:1]
        if not inbound_method:
            raise UserError(
                _(
                    "The journal '%s' needs an inbound payment method of type 'Third Party Check (in)' "
                    "to receive rejected checks from the supplier."
                )
                % self.rejected_journal_id.display_name
            )

        last_operation = check._get_last_operation()
        vendor = last_operation.partner_id if last_operation else check.payment_id.partner_id

        memo = _("Check rejection - recovery from supplier: %s") % check.name
        return self.env["account.payment"].create(
            {
                "date": self.date,
                "amount": check.amount,
                "currency_id": check.currency_id.id,
                "partner_id": vendor.id,
                "payment_type": "inbound",
                "partner_type": "supplier",
                "journal_id": self.rejected_journal_id.id,
                "payment_method_line_id": inbound_method.id,
                "memo": memo,
                "l10n_latam_move_check_ids": [Command.link(check.id)],
            }
        )

    def _create_bank_transfer_payment(self, check):
        """Case B: Create an outgoing transfer (internal transfer) from the bank to the rejected_journal."""
        bank_journal = check.current_journal_id
        out_method = bank_journal._get_available_payment_method_lines("outbound").filtered(
            lambda x: x.code in ("out_third_party_checks", "return_third_party_checks")
        )[:1]
        if not out_method:
            raise UserError(
                _(
                    "The journal '%s' needs an outbound payment method compatible with third-party checks "
                    "(e.g. 'out_third_party_checks') to transfer the rejected check."
                )
                % bank_journal.display_name
            )

        in_method = self.rejected_journal_id._get_available_payment_method_lines("inbound").filtered(
            lambda x: x.code == "in_third_party_checks"
        )[:1]
        if not in_method:
            raise UserError(
                _(
                    "The journal '%s' needs an inbound payment method of type 'Third Party Check (in)' "
                    "to receive the transferred rejected check."
                )
                % self.rejected_journal_id.display_name
            )

        memo = _("Check rejection - bank transfer: %s") % check.name
        return self.env["account.payment"].create(
            {
                "date": self.date,
                "amount": check.amount,
                "currency_id": check.currency_id.id,
                "partner_id": self.env.company.partner_id.id,
                "payment_type": "outbound",
                "journal_id": bank_journal.id,
                "is_internal_transfer": True,
                "destination_journal_id": self.rejected_journal_id.id,
                "payment_method_line_id": out_method.id,
                "memo": memo,
                "l10n_latam_move_check_ids": [Command.link(check.id)],
            }
        )

    def _create_customer_return_payment(self, check):
        """Create outbound payment from rejected_journal to return the check to the customer (generates AR debt)."""
        available_outbound_methods = self.rejected_journal_id._get_available_payment_method_lines("outbound")
        return_method = available_outbound_methods.filtered(lambda x: x.code == "return_third_party_checks")[:1]
        if not return_method:
            return_method = available_outbound_methods.filtered(lambda x: x.code == "out_third_party_checks")[:1]
        if not return_method:
            raise UserError(
                _(
                    "The journal '%s' needs an outbound payment method of type 'Return Third Party Check' "
                    "or 'Third Party Check (out)' to return the rejected check to the customer and generate the debt."
                )
                % self.rejected_journal_id.display_name
            )

        customer = check.payment_id.partner_id
        memo = _("Check rejection - customer debit: %s") % check.name
        return self.env["account.payment"].create(
            {
                "date": self.date,
                "amount": check.amount,
                "currency_id": check.currency_id.id,
                "partner_id": customer.id,
                "payment_type": "outbound",
                "partner_type": "customer",
                "journal_id": self.rejected_journal_id.id,
                "payment_method_line_id": return_method.id,
                "memo": memo,
                "l10n_latam_move_check_ids": [Command.link(check.id)],
            }
        )
