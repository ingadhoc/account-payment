##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestSessionLifecycle(CashboxCommon):
    def test_session_lifecycle(self):
        """Dado una caja sin control de caja, cuando se recorre el ciclo de vida
        completo de una sesión, entonces cada paso deja el estado, las fechas y
        los saldos que declara.

        Va en cadena y no suelto porque lo que hay que verificar no es cada paso
        aislado sino que el estado **sobreviva a la secuencia**: la fecha de
        apertura que no se repisa al reabrir, y el cierre que estampa la fecha
        aun sin diarios de control.

        Cubre los comportamientos 5, 8, 10, 16 y 19 del relevamiento oba-test de
        account_cashbox.
        """
        cashbox = self._create_cashbox("Ciclo de vida", self.journal_cash | self.journal_bank)
        session = self._create_session(cashbox)

        with self.subTest("crear la sesión la numera con la secuencia de la caja y arma una línea por diario"):
            self.assertTrue(
                session.name.startswith(cashbox.sequence_id.prefix),
                "La sesión se llama %s y la secuencia de la caja tiene prefijo %s"
                % (session.name, cashbox.sequence_id.prefix),
            )
            self.assertEqual(session.state, "draft")
            self.assertEqual(session.line_ids.mapped("journal_id"), self.journal_cash | self.journal_bank)
            self.assertFalse(session.opening_date)
            self.assertFalse(session.closing_date)
            self.assert_cashbox_invariants(session)

        with self.subTest("abrirla la pasa a abierta y estampa la fecha de apertura"):
            session.with_user(self.cashbox_user).action_account_cashbox_session_open()
            self.assertEqual(session.state, "opened")
            self.assertTrue(session.opening_date)
            primera_apertura = session.opening_date

        with self.subTest("un pago posteado suma al saldo final de la línea de su diario, y solo de ese"):
            payment = self._create_payment(self.journal_cash, amount=150.0, session=session)
            linea_cash = session.line_ids.filtered(lambda line: line.journal_id == self.journal_cash)
            linea_bank = session.line_ids.filtered(lambda line: line.journal_id == self.journal_bank)
            self.assertEqual(linea_cash.amount, 150.0)
            self.assertEqual(linea_cash.balance_end, 150.0)
            self.assertEqual(linea_bank.amount, 0.0, "El pago del diario de caja movió el saldo del diario de banco")
            self.assert_payment_invariants(payment)
            self.assert_cashbox_invariants(session)

        with self.subTest("cerrarla sin diarios de control igual estampa la fecha de cierre"):
            self.assertFalse(session.require_cash_control)
            session.with_user(self.cashbox_user).action_account_cashbox_session_close()
            self.assertEqual(session.state, "closed")
            self.assertTrue(
                session.closing_date,
                "La sesión cerró sin estampar la fecha de cierre: sin diarios de control nadie pasa por el "
                "control de cierre, que es donde la otra rama la estampa",
            )

        with self.subTest("volverla a borrador y reabrirla no repisa la fecha de apertura original"):
            session.action_account_cashbox_session_reset_to_draft()
            self.assertEqual(session.state, "draft")
            session.with_user(self.cashbox_user).action_account_cashbox_session_open()
            self.assertEqual(session.state, "opened")
            self.assertEqual(
                session.opening_date,
                primera_apertura,
                "Reabrir la sesión repisó la fecha de apertura original",
            )
            self.assert_cashbox_invariants(session)

        with self.subTest("una sesión que no está en borrador no se puede borrar"):
            with self.assertRaises(UserError):
                session.unlink()

        with self.subTest("una sesión en borrador sí se puede borrar"):
            # en otra caja: la de arriba tiene una sesión abierta y no permite concurrentes
            borrable = self._create_session(self._create_cashbox("Borrable", self.journal_cash))
            borrable.unlink()
            self.assertFalse(borrable.exists())
