##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestPaymentBinding(CashboxCommon):
    """Enganche entre el pago y la sesión de caja.

    Todos los pagos se crean con ``cashbox_user``: el dominio de sesiones
    disponibles se evalúa contra el usuario en curso, así que crear como
    superusuario mediría otra cosa. Y todas las cajas de la suite restringen
    usuarios, así que las sesiones que la base ya tuviera abiertas no entran en
    el dominio de este usuario — la aislación es por construcción, no por
    asserts flojos.
    """

    def _pago_desde_formulario(self, journal, amount=100.0):
        """Carga un pago como lo carga el usuario, por el formulario.

        Va por ``Form`` y no por ``create()`` a propósito: la asignación
        automática de la sesión **solo ocurre por el formulario**. En un
        ``create()`` programático el campo queda vacío, porque se computa antes
        de que esté seteada la compañía del pago y el dominio de sesiones
        disponibles sale vacío. Está reportado como hallazgo del relevamiento;
        el test no lo blinda ni lo tapa: verifica el camino del usuario, que es
        el que tiene comportamiento definido.
        """
        form = Form(self.env["account.payment"].with_user(self.cashbox_user))
        form.partner_id = self.partner
        form.journal_id = journal
        form.amount = amount
        return form

    def test_el_pago_toma_la_sesion_disponible(self):
        """Dado un pago nuevo, cuando hay una, varias o ninguna sesión disponible,
        entonces toma la única, la de la caja por defecto del usuario, o ninguna.

        Cubre el comportamiento 22 del relevamiento oba-test de account_cashbox.
        """
        caja_a = self._create_cashbox("Binding A", self.journal_cash)
        sesion_a = self._create_session(caja_a, open_it=True)

        with self.subTest("con una sola sesión disponible el pago la toma solo"):
            self.assertEqual(self._pago_desde_formulario(self.journal_cash).cashbox_session_id, sesion_a)

        caja_b = self._create_cashbox("Binding B", self.journal_cash)
        sesion_b = self._create_session(caja_b, open_it=True)

        with self.subTest("con dos sesiones disponibles el pago toma la de la caja por defecto del usuario"):
            self.cashbox_user.default_cashbox_id = caja_b
            self.assertEqual(
                self._pago_desde_formulario(self.journal_cash).cashbox_session_id,
                sesion_b,
                "Con dos sesiones disponibles el pago no cayó en la sesión de la caja por defecto del usuario",
            )

        with self.subTest("sin ninguna sesión disponible el pago queda sin sesión"):
            self.cashbox_user.default_cashbox_id = False
            for sesion in (sesion_a, sesion_b):
                sesion.action_account_cashbox_session_close()
            self.assertFalse(self._pago_desde_formulario(self.journal_cash).cashbox_session_id)

    def test_el_usuario_obligado_a_usar_sesion_no_postea_sin_sesion(self):
        """Dado un usuario obligado a operar con sesión de caja, cuando postea un
        pago sin sesión abierta, entonces se rechaza.

        Cubre el comportamiento 24 del relevamiento oba-test de account_cashbox.
        """
        self.cashbox_user.requiere_account_cashbox_session = True
        pago = self._create_payment(self.journal_cash, post=False)
        self.assertFalse(pago.cashbox_session_id, "El escenario declara que no hay ninguna sesión abierta")
        with self.assertRaises(UserError):
            pago.with_user(self.cashbox_user).action_post()

    def test_no_se_postea_ni_se_cancela_contra_una_sesion_que_no_esta_abierta(self):
        """Dado una sesión que no está abierta, cuando se postea o se cancela un
        pago suyo, entonces se rechaza.

        Son los dos bordes del mismo mecanismo —la sesión como ventana temporal
        de lo que se puede tocar— y por eso van juntos.

        Cubre los comportamientos 25 y 26 del relevamiento oba-test de
        account_cashbox.
        """
        cashbox = self._create_cashbox("Ventana de la sesión", self.journal_cash)
        session = self._create_session(cashbox)

        with self.subTest("no se postea un pago sobre una sesión que sigue en borrador"):
            pago = self._create_payment(self.journal_cash, session=session, post=False)
            with self.assertRaises(UserError):
                pago.with_user(self.cashbox_user).action_post()

        with self.subTest("no se cancela un pago de una sesión ya cerrada"):
            session.action_account_cashbox_session_open()
            posteado = self._create_payment(self.journal_cash, amount=50.0, session=session)
            session.action_account_cashbox_session_close()
            self.assertEqual(session.state, "closed")
            with self.assertRaises(UserError):
                posteado.action_cancel()

    def test_los_diarios_del_pago_se_limitan_a_los_de_la_sesion(self):
        """Dado una sesión vieja y una caja a la que después le agregaron un diario,
        cuando se listan los diarios disponibles del pago, entonces salen los de
        las **líneas de la sesión**, no los de la caja.

        Ese es el borde que el propio código declara en su comentario: la sesión
        conserva los diarios con los que nació. Con una caja que nunca cambió,
        las dos listas coinciden y el test no verificaría nada.

        Cubre el comportamiento 27 del relevamiento oba-test de account_cashbox.
        """
        cashbox = self._create_cashbox("Diarios de la sesión", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        self.assertEqual(session.line_ids.mapped("journal_id"), self.journal_cash)

        # la caja cambia después de abierta la sesión: la sesión no se entera, y está bien
        cashbox.journal_ids = [Command.set((self.journal_cash | self.journal_bank).ids)]

        pago = self._create_payment(self.journal_cash, session=session, post=False)
        self.assertIn(self.journal_cash, pago.available_journal_ids)
        self.assertNotIn(
            self.journal_bank,
            pago.available_journal_ids,
            "El pago ofrece un diario que se agregó a la caja después de abierta la sesión",
        )

    def test_la_moneda_del_pago_debe_ser_la_del_diario(self):
        """Dado un diario con moneda propia y una sesión, cuando el pago va en otra
        moneda, entonces se rechaza.

        Cubre el comportamiento 29 del relevamiento oba-test de account_cashbox.
        """
        journal = self._create_journal("Test Cashbox TCB3", "TCBH", "cash", currency=self.foreign_currency)
        cashbox = self._create_cashbox("Moneda del diario", journal)
        session = self._create_session(cashbox, open_it=True)

        with self.assertRaises(ValidationError):
            self._create_payment(journal, session=session, post=False, currency_id=self.currency.id)

    def test_importar_pagos_los_ata_a_la_sesion_y_deja_nota(self):
        """Dado pagos sueltos, cuando se los importa a una sesión, entonces quedan
        atados a ella y la sesión deja constancia en el chatter.

        Cubre el comportamiento 33 del relevamiento oba-test de account_cashbox.
        """
        cashbox = self._create_cashbox("Importar pagos", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        suelto = self._create_payment(self.journal_cash, amount=70.0, session=False, post=False)
        self.assertFalse(suelto.cashbox_session_id)

        mensajes_antes = len(session.message_ids)
        wizard = self.env["account.cashbox.payment.import"].create(
            {"cashbox_session_id": session.id, "payment_ids": [Command.set(suelto.ids)]}
        )
        wizard.action_import_payment()

        self.assertEqual(suelto.cashbox_session_id, session)
        self.assertEqual(
            len(session.message_ids), mensajes_antes + 1, "La importación no dejó constancia en el chatter"
        )
        self.assertIn(self.journal_cash.display_name, session.message_ids[0].body)

    def test_el_wizard_de_registro_propaga_la_sesion(self):
        """Dado el wizard de registro de pagos con una sesión elegida, cuando se
        registra el pago, entonces el pago creado sale con esa sesión.

        Es el camino que usan los módulos que siguen registrando pagos por el
        wizard estándar (gastos, por ejemplo), no por el flujo propio de caja.

        Cubre el comportamiento 37 del relevamiento oba-test de account_cashbox.
        """
        cashbox = self._create_cashbox("Wizard de registro", self.journal_cash)
        session = self._create_session(cashbox, open_it=True)
        invoice = self._create_invoice(amount=120.0)

        wizard = (
            self.env["account.payment.register"]
            .with_user(self.cashbox_user)
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create({"journal_id": self.journal_cash.id, "cashbox_session_id": session.id})
        )
        pagos = wizard._create_payments()

        self.assertEqual(len(pagos), 1)
        self.assertEqual(
            pagos.cashbox_session_id,
            session,
            "El pago creado por el wizard de registro no se enganchó a la sesión elegida en el wizard",
        )
        self.assert_cashbox_invariants(session)
