from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import formatLang


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed_check_payment(self):
        """No dejar borrar el asiento de un pago con cheques mientras el pago sigue confirmado.

        Si se borra el asiento y se vuelve a postear el pago (account_ux regenera el asiento que
        falta), el cheque queda con el diario actual equivocado: ``current_journal_id`` se computa
        con la última operación del cheque ordenada por ``(date, write_date, id)``, y el repost
        manda al final el ``write_date`` de la operación reposteada, así que una recepción vieja
        pasa a tapar la transferencia posterior. Para ajustar el asiento hay que restablecer el
        pago a borrador, que es el camino que recomputa las operaciones del cheque.

        Igual que en los ondelete de core, ``force_delete`` sigue siendo la salida programática
        (por ejemplo el borrado del asiento en borrador que hace ``account.payment.action_cancel``).
        """
        if self._context.get("force_delete"):
            return
        payments = self.origin_payment_id.filtered(
            lambda payment: payment._is_latam_check_payment() and payment.state not in ("draft", "canceled")
        )
        if payments:
            raise UserError(
                _(
                    "You cannot delete the journal entry of a payment with checks while the payment is confirmed. "
                    "If you need to adjust the journal entry, reset the payment to draft first.\n"
                    "Payments:\n%s",
                    "\n".join("* %s" % payment.display_name for payment in payments),
                )
            )

    def _build_credit_warning_message(self, record, current_amount=0.0, exclude_current=False, exclude_amount=0.0):
        """Add the third party checks on hand to the credit limit warning.

        They go on top of the amount of the document instead of the partner ``credit``, which is
        the accounting debt and must match the partner ledger. Passing them through
        ``current_amount`` keeps them working when another module rewrites the total without
        calling super. Invoices and sales orders both build their warning here.

        With ``checks_in_credit`` in the context the total already carries the checks (see
        ``sale_exception_credit_limit_latam_check``) and this override leaves the warning alone.
        """
        if self.env.context.get("checks_in_credit"):
            return super()._build_credit_warning_message(
                record, current_amount=current_amount, exclude_current=exclude_current, exclude_amount=exclude_amount
            )
        partner = record.partner_id.commercial_partner_id
        checks_amount = partner._get_on_hand_checks_credit(record.company_id) if partner else 0.0
        message = super()._build_credit_warning_message(
            record,
            current_amount=current_amount + checks_amount,
            exclude_current=exclude_current,
            exclude_amount=exclude_amount,
        )
        return self._add_checks_credit_warning_line(message, checks_amount, record.company_id)

    def _add_checks_credit_warning_line(self, message, checks_amount, company):
        if not message or not checks_amount:
            return message
        return (
            message
            + "\n"
            + _(
                "Includes third party checks on hand: %(amount)s",
                amount=formatLang(self.env, checks_amount, currency_obj=company.currency_id),
            )
        )
