##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestCashboxSecurity(CashboxCommon):
    def _assert_bloqueado_por_el_modulo(self, accion):
        """El bloqueo lo pone el módulo, no el ACL.

        ``AccessError`` hereda de ``UserError``, así que un ``assertRaises
        (UserError)`` pelado acepta las dos cosas indistintamente y no
        distingue "el módulo lo frenó" de "el usuario no tenía permiso de
        escritura igual". Esa laxitud deja pasar el caso en que alguien saca la
        verificación del módulo: el test sigue verde porque el ACL tapa el
        agujero, hasta que a alguien le dan permiso de escritura.
        """
        with self.assertRaises(UserError) as capturado:
            accion()
        self.assertNotIsInstance(
            capturado.exception,
            AccessError,
            "El intento lo frenó el control de acceso genérico y no la verificación de la caja: "
            "el mensaje fue %s" % capturado.exception,
        )

    def test_usuario_de_solo_lectura_ve_pero_no_opera(self):
        """Dado un usuario habilitado solo para ver los pagos de una caja, cuando
        intenta operarla, entonces el sistema lo bloquea; y solo ve las sesiones
        de esa caja.

        Es un **control positivo**: lo que se verifica es que el sistema
        *bloquee*. Sin esto, una suite deja pasar el arreglo que bloquea de más
        —"lo arreglé" puede significar "lo apagué"— y también el que no bloquea
        nada, que es el estado en el que estaba este módulo.

        Cubre los comportamientos 17 y 39 del relevamiento oba-test de
        account_cashbox.
        """
        caja_visible = self._create_cashbox("Caja del viewer", self.journal_cash)
        caja_visible.allowed_users_view_payments = [(6, 0, self.viewer_user.ids)]
        caja_ajena = self._create_cashbox("Caja ajena", self.journal_bank)

        sesion_visible = self._create_session(caja_visible, open_it=True)
        sesion_ajena = self._create_session(caja_ajena, open_it=True)

        with self.subTest("el usuario de solo-lectura ve las sesiones de su caja y no ve las de otra caja"):
            visibles = (
                self.env["account.cashbox.session"]
                .with_user(self.viewer_user)
                .search([("id", "in", (sesion_visible | sesion_ajena).ids)])
            )
            # igualdad exacta contra los registros que creó el test: nunca "hay al menos una"
            self.assertEqual(
                visibles,
                sesion_visible,
                "El usuario de solo-lectura ve %s y solo debería ver la sesión de su caja" % visibles.mapped("name"),
            )

        with self.subTest("el usuario de solo-lectura no puede abrir una sesión"):
            # en otra caja: caja_visible no permite concurrentes y ya tiene su sesión abierta
            otra_caja = self._create_cashbox("Caja del viewer 2", self.journal_cash)
            otra_caja.allowed_users_view_payments = [(6, 0, self.viewer_user.ids)]
            en_borrador = self._create_session(otra_caja, open_it=False)
            self._assert_bloqueado_por_el_modulo(
                en_borrador.with_user(self.viewer_user).action_account_cashbox_session_open
            )

        with self.subTest("el usuario de solo-lectura no puede pasar a control de cierre ni cerrar"):
            self._assert_bloqueado_por_el_modulo(sesion_visible.with_user(self.viewer_user).action_closing_control)
            self._assert_bloqueado_por_el_modulo(
                sesion_visible.with_user(self.viewer_user).action_account_cashbox_session_close
            )

        with self.subTest("el usuario de solo-lectura no puede escribir la sesión"):
            with self.assertRaises(AccessError):
                sesion_visible.with_user(self.viewer_user).write({"name": "Renombrada por el viewer"})

    def test_configuracion_de_la_caja_se_protege(self):
        """Dado una caja configurada, cuando se la modifica de formas que dejarían
        datos inconsistentes, entonces el sistema las rechaza.

        Cubre los comportamientos 1, 2 y 3 del relevamiento oba-test de
        account_cashbox.
        """
        cashbox = self._create_cashbox(
            "Configuración protegida",
            self.journal_cash | self.journal_bank,
            cash_control_journal_ids=[(6, 0, self.journal_cash.ids)],
        )

        with self.subTest("no se saca de la caja un diario que tiene control de apertura y cierre"):
            with self.assertRaises(UserError):
                cashbox.journal_ids = [(6, 0, self.journal_bank.ids)]

        with self.subTest("desmarcar restringir usuarios vacía la lista de usuarios permitidos"):
            self.assertTrue(cashbox.allowed_res_users_ids)
            cashbox.restrict_users = False
            self.assertFalse(
                cashbox.allowed_res_users_ids,
                "La caja dejó de restringir usuarios pero conservó la lista de permitidos",
            )

        with self.subTest("no se borra una caja que tiene sesiones"):
            self._create_session(cashbox)
            with self.assertRaises(UserError):
                cashbox.unlink()

    def test_la_sesion_no_acepta_usuarios_ajenos_a_la_caja(self):
        """Dado una caja que restringe usuarios, cuando se asigna a la sesión un
        usuario que no está permitido, entonces se rechaza.

        Cubre el comportamiento 18 del relevamiento oba-test de account_cashbox.
        La validación existía escrita pero estaba anidada dentro de
        ``_compute_line_ids``, así que el ORM nunca la registraba: se definía una
        función local en cada iteración del compute y se descartaba.
        """
        ajeno = self._create_user("cashbox_intruso", "Cashbox Intruso")
        cashbox = self._create_cashbox("Con usuarios restringidos", self.journal_cash)
        self.assertNotIn(ajeno, cashbox.allowed_res_users_ids)

        session = self._create_session(cashbox)
        with self.assertRaises(ValidationError):
            session.write({"user_ids": [(4, ajeno.id)]})
