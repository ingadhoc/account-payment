##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestCheckResetToDraft(LatamCheckCommon):
    """FCP-R09: volver a borrador un pago que tiene un cheque de por medio.

    Tres variantes de borde de FCP-R09 son específicas de cheques y quedaban
    sin cubrir en la batería genérica de ``account_payment_pro`` (que resuelve
    R09-E1/E7/E8/E9 sin cheques):

    - E3: el cheque no tuvo ninguna operación posterior — volver a borrador
      tiene que funcionar limpio.
    - E4 (control positivo): el cheque propio ya fue debitado — volver a
      borrador tiene que bloquear, nombrando el cheque y su estado.
    - E5: el cheque de terceros tiene una operación posterior (un pase de
      cartera) — volver a borrador el cobro original tiene que bloquear
      hasta que se revierta esa operación posterior.

    Cubre FCP-R09-E3/E4/E5.
    Tickets 120230, 120501, 121622, 121844, 122207 (mismos que R09 base).
    """

    def test_a_check_with_no_later_operation_resets_cleanly(self):
        """Dado un cobro con un cheque de terceros recién recibido (ninguna
        operación posterior), cuando se restablece a borrador, entonces no
        hay error, el cheque deja de estar en cartera (no queda ninguna
        operación no-borrador que lo ubique), y al re-confirmar vuelve a
        quedar en la misma cartera que antes.

        Cubre FCP-R09-E3.
        """
        receipt = self._receive_third_party_checks([20000.0], numbers=["00000901"])
        receipt.action_post()
        self.assert_payment_invariants(receipt, "cobro del cheque")
        check = receipt.l10n_latam_new_check_ids

        with self.subTest("recién cobrado, el cheque está en la cartera del cobro"):
            self.assertEqual(check.current_journal_id, self.third_party_journal)

        receipt.action_draft()
        check.invalidate_recordset()

        with self.subTest("vuelto a borrador sin error"):
            self.assertEqual(receipt.state, "draft")
        with self.subTest("sin operación confirmada, el cheque ya no está en ninguna cartera"):
            self.assertFalse(check.current_journal_id)

        receipt.action_post()
        self.assert_payment_invariants(receipt, "cobro re-confirmado")
        check.invalidate_recordset()

        with self.subTest("re-confirmado, el cheque vuelve a la misma cartera"):
            self.assertEqual(check.current_journal_id, self.third_party_journal)
            self.assertEqual(check.payment_id, receipt, "el cheque sigue colgado del mismo cobro")

    def test_a_debited_check_blocks_the_reset(self):
        """Dado un pago con un cheque propio ya debitado, cuando se intenta
        restablecer a borrador, entonces bloquea con un error que nombra el
        cheque y su estado — no lo deja volver a borrador dejando el débito
        colgado de un pago inexistente.

        Cubre FCP-R09-E4 (control positivo).
        """
        payment = self._create_own_check_payment([50000.0], numbers=["00000902"])
        payment.action_post()
        self.assert_payment_invariants(payment, "emisión del cheque propio")
        check = payment.l10n_latam_new_check_ids

        self.env["account.check.action.wizard"].with_context(
            active_model="l10n_latam.check", active_ids=check.ids
        ).create({"date": self.today}).action_confirm()
        check.invalidate_recordset()
        self.assertEqual(check.issue_state, "debited")
        debit_move = self.env["account.move.line"].search([("name", "=", f"Débito cheque nro {check.name}")]).move_id
        self.assert_no_automatic_balancing_line(debit_move, "débito del cheque %s" % check.name)
        self.assert_no_zero_lines(debit_move, "débito del cheque %s" % check.name)

        with self.assertRaisesRegex(UserError, check.name):
            payment.action_draft()

    def test_a_check_with_a_later_transfer_blocks_the_reset_until_reverted(self):
        """Dado un cobro con un cheque de terceros que después se pasó a otra
        cartera, cuando se intenta restablecer el cobro original a borrador,
        entonces bloquea (la operación posterior lo impide); revertido ese
        pase, el cobro original sí puede restablecerse a borrador.

        Cubre FCP-R09-E5.
        """
        other_journal = self._create_third_party_journal("Test Reset Other Wallet", "TROW")
        receipt = self._receive_third_party_checks([20000.0], numbers=["00000903"])
        receipt.action_post()
        self.assert_payment_invariants(receipt, "cobro del cheque")
        check = receipt.l10n_latam_new_check_ids

        outbound = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=check.ids)
            .create({"destination_journal_id": other_journal.id})
            ._create_payments()
        )
        # el pase es dos apuntes (outbound + su inbound emparejado); ambos tienen que ser sanos
        for payment in outbound + outbound.paired_internal_transfer_payment_id:
            self.assert_payment_invariants(payment, "pase de cartera")
        check.invalidate_recordset()
        with self.subTest("el cheque quedó en la cartera destino del pase"):
            self.assertEqual(check.current_journal_id, other_journal)

        with self.subTest("el cobro original no puede volver a borrador con el pase encima"):
            with self.assertRaises(UserError):
                receipt.action_draft()

        # revertir el pase se hace desde su lado inbound: resetearlo arrastra al outbound
        # emparejado (ver test_third_party_check_lifecycle._revert_last_transfer)
        transfer_inbound = check.operation_ids.filtered(
            lambda pay: pay.payment_type == "inbound" and pay.id != receipt.id and pay.state not in ("draft", "cancel")
        )
        transfer_inbound.action_draft()
        check.invalidate_recordset()

        with self.subTest("revertido el pase, el cobro original sí puede volver a borrador"):
            receipt.action_draft()
            self.assertEqual(receipt.state, "draft")
