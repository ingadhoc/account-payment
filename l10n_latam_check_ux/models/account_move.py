from odoo import _, api, models
from odoo.exceptions import UserError


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
