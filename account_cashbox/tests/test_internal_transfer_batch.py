##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestInternalTransferBatch(CashboxCommon):
    """Transferencias internas entre sesiones de caja, en los bordes que faltaban.

    El camino feliz de una transferencia con sesión destino ya está cubierto por
    ``test_internal_transfer_cashbox_session``. Acá van los dos casos que esa
    suite no puede detectar: un lote donde cada transferencia va a una sesión
    destino **distinta** (la suite actual manda las tres a la misma, así que un
    cruce entre pagos del lote pasaría en verde), y el onchange que limpia la
    sesión destino cuando deja de ser válida.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal_origen = cls._create_journal("Test Transfer Origen", "TTRO", "cash")
        cls.journal_destino_a = cls._create_journal("Test Transfer Destino A", "TTRA", "cash")
        cls.journal_destino_b = cls._create_journal("Test Transfer Destino B", "TTRB", "cash")

    def setUp(self):
        super().setUp()
        self.caja_origen = self._create_cashbox("Transfer origen", self.journal_origen)
        self.caja_a = self._create_cashbox("Transfer destino A", self.journal_destino_a)
        self.caja_b = self._create_cashbox("Transfer destino B", self.journal_destino_b)
        self.sesion_origen = self._create_session(self.caja_origen, open_it=True)
        self.sesion_a = self._create_session(self.caja_a, open_it=True)
        self.sesion_b = self._create_session(self.caja_b, open_it=True)

    def _transferencia(self, destino_journal, destino_sesion, amount):
        return self._create_payment(
            self.journal_origen,
            amount=amount,
            session=self.sesion_origen,
            post=False,
            is_internal_transfer=True,
            destination_journal_id=destino_journal.id,
            destination_cashbox_session_id=destino_sesion.id,
        )

    def test_un_lote_manda_cada_pareado_a_su_propia_sesion_destino(self):
        """Dado un lote de transferencias internas a sesiones destino distintas,
        cuando se postean juntas, entonces cada pago pareado cae en la sesión
        que le corresponde.

        Los importes son distintos entre sí a propósito: con importes iguales un
        cruce entre pagos del lote sería indistinguible del resultado correcto.

        Cubre el comportamiento 30c del relevamiento oba-test de account_cashbox.
        """
        esperado = {
            self._transferencia(self.journal_destino_a, self.sesion_a, 100.0): self.sesion_a,
            self._transferencia(self.journal_destino_b, self.sesion_b, 200.0): self.sesion_b,
            self._transferencia(self.journal_destino_a, self.sesion_a, 300.0): self.sesion_a,
        }
        pagos = self.env["account.payment"].browse([p.id for p in esperado])
        pagos.action_post()

        for pago, sesion_destino in esperado.items():
            pareado = pago.paired_internal_transfer_payment_id
            self.assertTrue(pareado, "La transferencia de %s no generó su pago pareado" % pago.amount)
            self.assertEqual(
                pareado.cashbox_session_id,
                sesion_destino,
                "El pareado de la transferencia de %s cayó en la sesión %s y la transferencia declaraba %s"
                % (pago.amount, pareado.cashbox_session_id.name, sesion_destino.name),
            )
            self.assertFalse(
                pareado.destination_cashbox_session_id,
                "El pago pareado quedó con sesión destino propia: encadenaría otra transferencia",
            )
            self.assert_payment_invariants(pago)
            self.assert_payment_invariants(pareado)

        self.assert_cashbox_invariants(self.sesion_a)
        self.assert_cashbox_invariants(self.sesion_b)

    def test_cambiar_el_diario_destino_limpia_la_sesion_que_dejo_de_valer(self):
        """Dado una transferencia con sesión destino elegida, cuando se cambia el
        diario destino por otro que esa sesión no controla, entonces la sesión
        destino se limpia.

        Sin esto la transferencia se postea contra una sesión que no maneja el
        diario al que entra la plata, y el importe queda fuera de todos los
        saldos de esa sesión.

        Cubre el comportamiento 31 del relevamiento oba-test de account_cashbox.
        """
        pago = self._transferencia(self.journal_destino_a, self.sesion_a, 150.0)
        self.assertEqual(pago.destination_cashbox_session_id, self.sesion_a)

        with self.subTest("cambiar a un diario que la sesión destino no controla la limpia"):
            pago.destination_journal_id = self.journal_destino_b
            pago._onchange_destination_journal_id()
            self.assertFalse(
                pago.destination_cashbox_session_id,
                "La sesión destino sobrevivió al cambio de diario y ya no controla ese diario",
            )

        with self.subTest("volver a un diario que sí controla y elegir su sesión la conserva"):
            pago.destination_journal_id = self.journal_destino_a
            pago.destination_cashbox_session_id = self.sesion_a
            pago._onchange_destination_journal_id()
            self.assertEqual(pago.destination_cashbox_session_id, self.sesion_a)

        with self.subTest("sin diario destino no queda sesión destino"):
            pago.destination_journal_id = False
            pago._onchange_destination_journal_id()
            self.assertFalse(pago.destination_cashbox_session_id)
