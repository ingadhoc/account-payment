##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestCashboxInvariants(CashboxCommon):
    """La batería de invariantes tiene que fallar cuando corresponde fallar.

    Es el test de la propia herramienta, y no es ceremonia: la batería la llaman
    todas las suites de caja, así que un error acá deja la suite entera en verde
    sin verificar nada. Por eso cada invariante se prueba en los dos sentidos:
    pasa con la operación sana y **falla** con la operación que tiene que
    detectar.

    Ya pagamos ese costo una vez: ``assert_no_automatic_balancing_line`` estaba
    escrita buscando la línea de relleno **por cuenta**, y
    ``_get_automatic_balancing_account()`` devuelve la cuenta del diario cuando
    el diario tiene una — o sea que daba positivo en todos los pagos de banco y
    caja. Se detectó porque la invariante se probó contra una operación sana.
    """

    def test_cobertura_de_lineas_detecta_un_diario_que_no_es_de_caja(self):
        cashbox = self._create_cashbox("Cobertura", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)

        with self.subTest("con la sesión sana no molesta"):
            self.assert_session_line_coverage(session)

        with self.subTest("detecta una línea de un diario que no es de banco ni de caja"):
            general = self._create_journal("Test Cashbox General", "TCBX", "general")
            self.env["account.cashbox.session.line"].create(
                {"cashbox_session_id": session.id, "journal_id": general.id}
            )
            with self.assertRaises(AssertionError):
                self.assert_session_line_coverage(session)

    def test_consistencia_de_saldos_detecta_un_pago_sin_linea(self):
        cashbox = self._create_cashbox("Consistencia", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        self._create_payment(self.journal_cash, amount=100.0, session=session)

        with self.subTest("con la sesión sana no molesta"):
            self.assert_session_balances_consistent(session)

        with self.subTest("detecta un pago en un diario que la sesión no controla"):
            # el importe de este pago no entra en ningún saldo de la sesión: al cerrar,
            # esa plata simplemente no se cuenta y nada falla
            huerfano = self._create_payment(self.journal_bank, amount=40.0, session=False)
            huerfano.cashbox_session_id = session
            with self.assertRaises(AssertionError):
                self.assert_session_balances_consistent(session)

    def test_la_bateria_de_asientos_detecta_la_linea_de_relleno(self):
        """La línea de relleno se busca por nombre, que es como la identifica Odoo.

        El caso sano es el que importa acá: un pago en un diario de caja tiene su
        línea de liquidez en ``journal.default_account_id``, que es justo lo que
        devuelve ``_get_automatic_balancing_account()``. Buscar por cuenta daría
        positivo siempre.
        """
        cashbox = self._create_cashbox("Relleno", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        pago = self._create_payment(self.journal_cash, amount=100.0, session=session)

        with self.subTest("un pago normal de caja no tiene línea de relleno"):
            self.assert_payment_invariants(pago)

        with self.subTest("detecta la línea que agrega Odoo cuando el asiento no cierra solo"):
            move = pago.move_id
            move.button_draft()
            cuenta = self.journal_cash.profit_account_id or self.journal_cash.default_account_id
            move.write(
                {
                    "line_ids": [
                        Command.create(
                            {
                                "name": self.env._("Automatic Balancing Line"),
                                "account_id": cuenta.id,
                                "debit": 0.0,
                                "credit": 0.0,
                            }
                        )
                    ]
                }
            )
            with self.assertRaises(AssertionError):
                self.assert_no_automatic_balancing_line(move)
