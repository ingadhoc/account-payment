##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestCashControlClosing(CashboxCommon):
    def _caja_con_control(self, name, journal, **kwargs):
        """Caja con control de apertura y cierre sobre `journal`.

        Ojo con ``max_diff``: su default es 0, y el chequeo rechaza toda
        diferencia mayor al tope. O sea que una caja recién creada **no puede
        cerrar con ninguna diferencia** y el wizard de ajuste nunca llega a
        abrirse. Los escenarios que van a buscar el ajuste declaran un tope
        holgado; los que van a buscar el tope lo declaran chico.
        """
        kwargs.setdefault("max_diff", 100.0)
        return self._create_cashbox(name, journal, cash_control_journal_ids=[(6, 0, journal.ids)], **kwargs)

    def test_cierre_con_control_de_caja(self):
        """Dado una sesión con diarios de control, cuando se la cierra contando la
        plata, entonces el control exige el conteo, el desvío abre el ajuste, y
        el ajuste deja un asiento sano.

        Va en cadena porque es donde el estado tiene que sobrevivir a la
        secuencia completa: control de cierre, ajuste, y vuelta a borrador que
        deshace el asiento.

        Cubre los comportamientos 9, 11, 12, 15 y 34 del relevamiento oba-test de
        account_cashbox.
        """
        cashbox = self._caja_con_control("Control de caja", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        self._create_payment(self.journal_cash, amount=200.0, session=session)
        linea = session.line_ids

        with self.subTest("pasar a control de cierre estampa la fecha de cierre"):
            self.assertTrue(session.require_cash_control)
            session.action_closing_control()
            self.assertEqual(session.state, "closing_control")
            self.assertTrue(session.closing_date)

        with self.subTest("validar sin haber cargado el saldo real de un diario controlado se rechaza"):
            with self.assertRaises(UserError):
                session.action_account_cashbox_session_close()
            self.assertEqual(session.state, "closing_control", "La sesión avanzó de estado pese al rechazo")

        with self.subTest("con diferencia el cierre devuelve el wizard de ajuste en vez de cerrar"):
            # se contaron 30 de más
            linea.balance_end_real = 230.0
            self.assertEqual(linea.balance_difference, 30.0)
            action = session.action_account_cashbox_session_close()
            self.assertEqual(action.get("res_model"), "account.cashbox.rounding.adjustment.wizard")
            self.assertEqual(session.state, "closing_control", "La sesión cerró sin pasar por el ajuste")

        with self.subTest("el ajuste crea un asiento contra la cuenta de ganancia del diario y cierra la sesión"):
            wizard = self.env["account.cashbox.rounding.adjustment.wizard"].browse(action["res_id"])
            wizard.action_create_journal_entries()
            self.assertEqual(session.state, "closed")

            asientos = self.env["account.move"].search([("cashbox_session_id", "=", session.id)])
            self.assertEqual(
                len(asientos),
                1,
                "El ajuste dejó %s asientos y la sesión tiene una sola línea con " "diferencia" % len(asientos),
            )
            self.assertEqual(asientos.state, "posted")
            self.assert_move_sums_zero(asientos)
            self.assert_no_automatic_balancing_line(asientos)
            self.assert_no_zero_lines(asientos)
            # se contó de más: entra plata a la cuenta del diario contra la cuenta de ganancia
            ganancia = asientos.line_ids.filtered(lambda x: x.account_id == self.journal_cash.profit_account_id)
            liquidez = asientos.line_ids.filtered(lambda x: x.account_id == self.journal_cash.default_account_id)
            self.assertEqual(ganancia.credit, 30.0)
            self.assertEqual(liquidez.debit, 30.0)

        with self.subTest("volver la sesión a borrador borra el asiento de ajuste"):
            session.action_account_cashbox_session_reset_to_draft()
            self.assertEqual(session.state, "draft")
            self.assertFalse(
                asientos.exists(),
                "La sesión volvió a borrador pero el asiento de ajuste quedó vivo: el próximo cierre sumaría "
                "un segundo ajuste sobre la misma diferencia",
            )

    def test_ajuste_puede_cerrar_sin_generar_asientos(self):
        """Dado una sesión con diferencia, cuando se elige cerrar sin asientos,
        entonces la sesión queda cerrada y no se creó ningún asiento.

        Cubre el comportamiento 36 del relevamiento oba-test de account_cashbox.
        """
        cashbox = self._caja_con_control("Cierre sin asientos", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        self._create_payment(self.journal_cash, amount=100.0, session=session)
        session.line_ids.balance_end_real = 90.0
        session.action_closing_control()
        action = session.action_account_cashbox_session_close()

        wizard = self.env["account.cashbox.rounding.adjustment.wizard"].browse(action["res_id"])
        wizard.action_close_without_entries()

        self.assertEqual(session.state, "closed")
        self.assertFalse(
            self.env["account.move"].search([("cashbox_session_id", "=", session.id)]),
            "Se eligió cerrar sin asientos y sin embargo quedó un asiento asociado a la sesión",
        )

    def test_tope_de_diferencia_en_moneda_de_la_compania(self):
        """Dado una caja con diferencia máxima configurada, cuando la diferencia la
        supera, entonces el cierre se rechaza.

        Cubre el comportamiento 13 del relevamiento oba-test de account_cashbox.
        """
        cashbox = self._caja_con_control("Tope en la moneda de la compania", self.journal_cash, max_diff=10.0)
        session = self._create_session(cashbox, open_it=True)
        self._create_payment(self.journal_cash, amount=100.0, session=session)
        session.action_closing_control()

        with self.subTest("una diferencia dentro del tope no se rechaza"):
            session.line_ids.balance_end_real = 105.0
            action = session.action_account_cashbox_session_close()
            self.assertEqual(action.get("res_model"), "account.cashbox.rounding.adjustment.wizard")

        with self.subTest("una diferencia que supera el tope se rechaza"):
            session.line_ids.balance_end_real = 130.0
            with self.assertRaises(ValidationError):
                session.action_account_cashbox_session_close()

    def test_tope_de_diferencia_en_diario_en_moneda_extranjera(self):
        """Dado un diario en moneda extranjera, cuando se compara la diferencia
        contra el tope, entonces el tope se lleva a la moneda del diario.

        El tope se configura en la moneda de la compañía (lo dice el help del
        campo ``max_diff``) y la diferencia de la línea viene en la moneda del
        diario. Con la cotización de la suite —1 de la compañía = 2 TCB— un tope
        de 10 vale 20 TCB: una diferencia de 15 TCB entra y una de 25 TCB no.

        Cubre los comportamientos 13 y 21 del relevamiento oba-test de
        account_cashbox.
        """
        journal = self._create_journal("Test Cashbox TCB", "TCBF", "cash", currency=self.foreign_currency)
        cashbox = self._caja_con_control("Tope en moneda", journal, max_diff=10.0)
        session = self._create_session(cashbox, open_it=True)
        self._create_payment(journal, amount=100.0, session=session, currency_id=self.foreign_currency.id)

        linea = session.line_ids
        self.assertEqual(linea.currency_id, self.foreign_currency, "La línea no tomó la moneda del diario")
        self.assertEqual(linea.balance_end, 100.0, "El saldo de un diario con moneda propia no está en esa moneda")
        session.action_closing_control()

        with self.subTest("una diferencia de 15 TCB entra en un tope de 10 de la compañía (20 TCB)"):
            linea.balance_end_real = 115.0
            action = session.action_account_cashbox_session_close()
            # hay diferencia, así que ofrece el ajuste: lo relevante es que no haya rechazado por el tope
            self.assertEqual(action.get("res_model"), "account.cashbox.rounding.adjustment.wizard")

        with self.subTest("una diferencia de 25 TCB supera ese mismo tope"):
            linea.balance_end_real = 125.0
            with self.assertRaises(ValidationError):
                session.action_account_cashbox_session_close()

    def test_ajuste_en_moneda_extranjera_usa_la_tasa_forzada(self):
        """Dado un diario en moneda extranjera, cuando se fuerza la tasa en el
        ajuste, entonces el asiento se valúa con esa tasa.

        Cubre el comportamiento 35 del relevamiento oba-test de account_cashbox.
        """
        journal = self._create_journal("Test Cashbox TCB2", "TCBG", "cash", currency=self.foreign_currency)
        cashbox = self._caja_con_control("Ajuste en moneda", journal)
        session = self._create_session(cashbox, open_it=True)
        self._create_payment(journal, amount=100.0, session=session, currency_id=self.foreign_currency.id)
        session.line_ids.balance_end_real = 120.0
        session.action_closing_control()
        action = session.action_account_cashbox_session_close()

        wizard = self.env["account.cashbox.rounding.adjustment.wizard"].browse(action["res_id"])
        wizard.write({"force_rate": True, "forced_rate": 0.5})
        wizard.action_create_journal_entries()

        asiento = self.env["account.move"].search([("cashbox_session_id", "=", session.id)])
        self.assertEqual(len(asiento), 1)
        # 20 TCB de diferencia a la tasa forzada 0,5 => 10 en la moneda de la compañía
        liquidez = asiento.line_ids.filtered(lambda x: x.account_id == journal.default_account_id)
        self.assertEqual(liquidez.debit, 10.0)
        self.assertEqual(liquidez.amount_currency, 20.0)
        self.assert_move_sums_zero(asiento)
        self.assert_no_zero_lines(asiento)
