##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestSessionConcurrency(CashboxCommon):
    def test_unicidad_y_arrastre_de_saldo(self):
        """Dado una caja con o sin sesiones concurrentes, cuando se abre la sesión
        siguiente, entonces la unicidad y el arrastre del saldo inicial se
        comportan según ese setting.

        Va parametrizado y no en dos archivos porque es **el mismo mecanismo en
        sus dos configuraciones**: duplicarlo duplicaría el fixture y el
        mantenimiento sin agregar una verificación nueva.

        El arrastre es lo que hace que la plata que quedó en la caja al cerrar
        anoche aparezca como saldo inicial esta mañana. Cubre los
        comportamientos 4, 6, 6b y 7 del relevamiento oba-test de
        account_cashbox.
        """
        for concurrentes in (False, True):
            with self.subTest("caja con sesiones concurrentes" if concurrentes else "caja sin sesiones concurrentes"):
                cashbox = self._create_cashbox(
                    "Arrastre %s" % concurrentes,
                    self.journal_cash,
                    cash_control_journal_ids=[(6, 0, self.journal_cash.ids)],
                    allow_concurrent_sessions=concurrentes,
                )

                primera = self._create_session(cashbox, open_it=True)
                self._create_payment(self.journal_cash, amount=100.0, session=primera)
                linea = primera.line_ids
                self.assertEqual(linea.balance_start, 0.0, "La primera sesión de la caja arrancó con saldo inicial")
                self.assertEqual(linea.balance_end, 100.0)

                # se cuenta la plata y coincide: cierra sin pasar por el ajuste
                linea.balance_end_real = 100.0
                primera.action_closing_control()
                primera.action_account_cashbox_session_close()
                self.assertEqual(primera.state, "closed")

                segunda = self._create_session(cashbox)
                arrastre = 0.0 if concurrentes else 100.0
                self.assertEqual(
                    segunda.line_ids.balance_start,
                    arrastre,
                    "La sesión siguiente arrancó con saldo inicial %s y la caja %s sesiones concurrentes"
                    % (segunda.line_ids.balance_start, "permite" if concurrentes else "no permite"),
                )
                self.assert_cashbox_invariants(segunda)

                segunda.action_account_cashbox_session_open()
                if concurrentes:
                    tercera = self._create_session(cashbox, name="Tercera concurrente", open_it=True)
                    self.assertEqual(
                        cashbox.current_concurrent_session_ids,
                        segunda | tercera,
                        "La caja con sesiones concurrentes no lista las dos sesiones abiertas",
                    )
                else:
                    with self.assertRaises(UserError):
                        self._create_session(cashbox, open_it=True)
                    self.assertEqual(
                        cashbox.current_session_id,
                        segunda,
                        "La sesión actual de la caja no es la única que quedó abierta",
                    )
