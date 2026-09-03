from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, common, tagged


@tagged("post_install", "-at_install")
class TestCashboxSessionAssignment(common.TransactionCase):
    """Asignación automática de cashbox_session_id en un pago (ticket 126172).

    La sesión que elige el sistema tiene que ser operable para ese pago: de la
    compañía del pago y de una caja que maneje su diario. Si no hay ninguna, el
    pago no se registra.

    Estos tests cubren el eje diario. Quedan declarados, sin test, dos escenarios:

    - El eje compañía (`company_id parent_of` y la cláusula de sucursales de
      `_get_available_domain`): no se puede demostrar en rojo aislando esa
      cláusula, nunca es la única defensa que descarta la sesión.
    - Postear un pago cuya sesión ya asignada está cerrada: hoy solo se verifica
      para la sesión destino de una transferencia interna.

    Falta la capa de invariantes (que el asiento cierre, sin líneas en cero):
    vive en AccountInvariantsMixin de account_ux y se engancha acá cuando mergee.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.journal = cls._create_journal("Cashbox Test Journal", "CBXTA")
        cls.other_journal = cls._create_journal("Cashbox Test Other Journal", "CBXTB")
        cls.income_account = cls.env["account.account"].create(
            {"name": "Cashbox Test Income", "code": "CBXTINC", "account_type": "income"}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Cashbox Test Partner"})
        # el usuario necesita sesión de caja en cada pago: es la config que dispara
        # la asignación automática en action_post
        cls.user = cls.env["res.users"].create(
            {
                "name": "Cashbox User",
                "login": "cashbox_user_test",
                "company_ids": [Command.set(cls.company.ids)],
                "company_id": cls.company.id,
                "group_ids": [Command.link(cls.env.ref("account.group_account_user").id)],
                "requiere_account_cashbox_session": True,
            }
        )

    @classmethod
    def _create_journal(cls, name, code, company=None):
        """Diario de caja con transitoria propia.

        Sin transitoria explícita, en las bases donde la cuenta de pendientes que hereda
        el método de pago es la misma que la transitoria del diario, el diario no se
        puede crear: lo frena la constraint de account_ux.
        """
        company = company or cls.company
        suspense = cls.env["account.account"].create(
            {
                "name": "%s Suspense" % name,
                "code": "%sSUS" % code,
                "account_type": "asset_current",
                "company_ids": [Command.set(company.ids)],
            }
        )
        return cls.env["account.journal"].create(
            {
                "name": name,
                "code": code,
                "type": "cash",
                "company_id": company.id,
                "suspense_account_id": suspense.id,
            }
        )

    @classmethod
    def _create_cashbox(cls, journal, **vals):
        return cls.env["account.cashbox"].create(
            dict(
                {
                    "name": "Caja %s" % journal.code,
                    "company_id": journal.company_id.id,
                    "journal_ids": [Command.link(journal.id)],
                    "allow_concurrent_sessions": True,
                },
                **vals,
            )
        )

    @classmethod
    def _open_session(cls, journal, cashbox=None, users=None):
        """Abre una sesión de `cashbox` (o de una caja nueva que maneja `journal`).

        `users=False` deja la sesión sin restricción de usuarios (operable por cualquiera).
        """
        Session = cls.env["account.cashbox.session"]
        if not cashbox:
            cashbox = cls._create_cashbox(journal)
        session = Session.create(
            {
                "cashbox_id": cashbox.id,
                "name": "S-%s" % Session.search_count([("cashbox_id", "=", cashbox.id)]),
                "user_ids": [Command.set(cls.user.ids if users is None else [])],
            }
        )
        session.action_account_cashbox_session_open()
        return session

    def _set_default_cashbox(self, cashbox):
        self.user.write({"allowed_cashbox_ids": [Command.link(cashbox.id)], "default_cashbox_id": cashbox.id})

    def _create_payment(self, journal=None):
        return (
            self.env["account.payment"]
            .with_user(self.user)
            .create(
                {
                    "journal_id": (journal or self.journal).id,
                    "partner_id": self.partner.id,
                    "amount": 100.0,
                    "date": fields.Date.today(),
                }
            )
        )

    def _post_invoice(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create(
                        {"name": "Cashbox test line", "account_id": self.income_account.id, "price_unit": 100.0}
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _register_model(self):
        """El wizard de registro, en el contexto de una factura publicada."""
        return (
            self.env["account.payment.register"]
            .with_user(self.user)
            .with_context(active_model="account.move", active_ids=self._post_invoice().ids)
        )

    def _register_wizard(self):
        return self._register_model().create({"journal_id": self.journal.id})

    def test_single_session_of_the_payment_journal_is_assigned(self):
        """Una sola sesión candidata, de una caja que maneja el diario: se asigna."""
        session = self._open_session(self.journal)

        payment = self._create_payment()
        payment.action_post()

        self.assertEqual(payment.cashbox_session_id, session)

    def test_single_session_of_another_journal_is_not_assigned(self):
        """Una sola sesión candidata, pero de una caja que no maneja el diario del pago:
        no se asigna, y sin sesión el pago no se puede registrar."""
        self._create_cashbox(self.journal)  # gestiona el diario del pago, pero sin sesión abierta
        self._open_session(self.other_journal)

        payment = self._create_payment()

        self.assertFalse(payment.available_cashbox_session_ids)
        with self.assertRaises(UserError):
            payment.action_post()
        self.assertFalse(payment.cashbox_session_id)

    def test_default_cashbox_session_of_another_journal_is_not_assigned(self):
        """Varias sesiones abiertas y caja por defecto de otro diario: no se asigna la
        sesión de la caja por defecto (era el bug: se tomaba sin validarla)."""
        self._create_cashbox(self.journal)  # gestiona el diario del pago, pero sin sesión abierta
        session = self._open_session(self.other_journal)
        self._open_session(self.other_journal, cashbox=session.cashbox_id)
        self._set_default_cashbox(session.cashbox_id)
        self.assertTrue(session.cashbox_id.current_session_id, "La caja por defecto tiene que tener sesión abierta")

        payment = self._create_payment()

        with self.assertRaises(UserError):
            payment.action_post()
        self.assertFalse(payment.cashbox_session_id)

    def test_default_cashbox_session_of_the_payment_journal_is_assigned(self):
        """Varias sesiones abiertas y caja por defecto que sí maneja el diario del pago:
        se sigue asignando su sesión actual (el caso de sesiones concurrentes no se rompe)."""
        session = self._open_session(self.journal)
        self._open_session(self.journal)
        self._set_default_cashbox(session.cashbox_id)

        payment = self._create_payment()
        payment.action_post()

        self.assertEqual(payment.cashbox_session_id, session)

    def test_journal_that_no_cashbox_manages_still_requires_a_session_and_blocks_posting(self):
        """La bandera es un espejo puro de la configuración del usuario: no se apaga porque el
        diario no tenga caja (esa distinción va solo en el mensaje del UserError). Sin caja no
        puede haber sesión posible, así que el pago queda bloqueado, no se registra sin sesión."""
        journal = self._create_journal("Cashbox Test Free Journal", "CBXTC")
        payment = self._create_payment(journal=journal)

        self.assertTrue(payment.requiere_account_cashbox_session)
        with self.assertRaisesRegex(UserError, "is not managed by any cashbox"):
            payment.action_post()
        self.assertEqual(payment.state, "draft")
        self.assertFalse(payment.cashbox_session_id)

    def test_journal_managed_by_a_cashbox_still_requires_a_session(self):
        """La contracara: si hay una caja que lo gestiona, la sesión se sigue exigiendo
        aunque no haya ninguna abierta. Si no, apagaríamos el control."""
        self._create_cashbox(self.journal)

        payment = self._create_payment()

        self.assertTrue(payment.requiere_account_cashbox_session)
        with self.assertRaisesRegex(UserError, "no open session"):
            payment.action_post()

    def test_cashbox_the_user_cannot_see_still_requires_a_session(self):
        """La caja existe pero una ir.rule se la esconde al usuario (no está entre sus
        usuarios permitidos). La sesión se sigue exigiendo: que la caja exista es
        configuración, no algo que dependa de quién mira. Sin el sudo del mensaje de
        action_post, acá el pago se hubiera registrado sin sesión creyendo que el diario no
        tiene caja."""
        other_user = self.env["res.users"].create(
            {"name": "Cashbox Other", "login": "cashbox_other_test", "company_ids": [Command.set(self.company.ids)]}
        )
        self._create_cashbox(self.journal, restrict_users=True, allowed_res_users_ids=[Command.set(other_user.ids)])

        payment = self._create_payment()

        self.assertFalse(
            self.env["account.cashbox"].with_user(self.user).search_count([("journal_ids", "=", self.journal.id)]),
            "El test necesita que la caja sea invisible para el usuario",
        )
        self.assertTrue(payment.requiere_account_cashbox_session)
        with self.assertRaisesRegex(UserError, "no open session"):
            payment.action_post()

    def test_register_wizard_does_not_assign_session_of_another_journal(self):
        """El wizard de registro escribe la sesión en los vals del pago, así que también
        tiene que descartar las sesiones de cajas que no manejan el diario."""
        self._open_session(self.other_journal)

        wizard = self._register_wizard()

        self.assertFalse(wizard.available_cashbox_session_ids)
        self.assertFalse(wizard.cashbox_session_id)

    def test_register_wizard_assigns_session_of_the_payment_journal(self):
        """La contracara: con la sesión abierta en una caja que sí maneja el diario del
        wizard, el pago que crea el wizard sale con esa sesión.

        La sesión va sin restricción de usuarios a propósito: `cashbox_session_id` es un
        compute almacenado, o sea `compute_sudo=True`, así que el `uid` con el que se
        evalúa el dominio no es el del usuario que registra y una sesión restringida a él
        no sería candidata. En el pago eso no se nota porque `action_post` llama al compute
        explícitamente, con el uid real.
        """
        session = self._open_session(self.journal, users=False)

        wizard = self._register_wizard()

        self.assertEqual(wizard.cashbox_session_id, session)
        payment = wizard._create_payments()
        self.assertEqual(payment.cashbox_session_id, session)

    def test_register_wizard_keeps_the_session_chosen_by_the_user(self):
        """El campo es editable en el wizard: si el usuario elige una sesión entre varias
        candidatas, el recálculo no se la puede pisar.

        Va por Form y no por write: la elección se hace en el formulario, que es donde
        corren los onchange que podrían recalcular el campo encima.
        """
        chosen = self._open_session(self.journal, users=False)
        self._open_session(self.journal, users=False)

        form = Form(self._register_model())
        form.journal_id = self.journal
        form.cashbox_session_id = chosen
        wizard = form.save()

        self.assertEqual(wizard.cashbox_session_id, chosen)
        self.assertEqual(wizard._create_payments().cashbox_session_id, chosen)

    def test_blank_payment_seeds_session_from_default_cashbox(self):
        """Un pago nuevo sin diario explícito (por ejemplo, creado a mano desde el formulario)
        arranca de la sesión de la caja por defecto del usuario en vez de al revés."""
        session = self._open_session(self.journal)
        self._set_default_cashbox(session.cashbox_id)

        payment = (
            self.env["account.payment"]
            .with_user(self.user)
            .create({"partner_id": self.partner.id, "amount": 100.0, "date": fields.Date.today()})
        )

        self.assertEqual(payment.cashbox_session_id, session)

    def test_payment_with_explicit_journal_does_not_get_seeded(self):
        """Si el caller ya fijó journal_id (wizard, transferencia, un create() directo), el
        default_get no lo pisa con la caja por defecto del usuario."""
        session = self._open_session(self.journal)
        self._set_default_cashbox(session.cashbox_id)
        self._open_session(self.other_journal)

        payment = self._create_payment(journal=self.other_journal)

        self.assertNotEqual(payment.journal_id, self.journal)

    def test_blank_payment_does_not_seed_session_from_another_company_default_cashbox(self):
        """La caja por defecto del usuario puede ser de otra compañía (multi-compañía sin
        jerarquía entre ellas, no sucursales). default_get no puede sembrar esa sesión: el
        pago se crea en la compañía activa del usuario, journal_id se resuelve ahí y nunca
        va a coincidir con la caja de la otra compañía — sin este chequeo quedaba un pago
        con sesión de una caja completamente ajena, que ningún compute posterior corrige."""
        other_company = self.env["res.company"].create({"name": "Cashbox Test Other Company"})
        self.user.write({"company_ids": [Command.link(other_company.id)]})
        other_journal = self._create_journal("Cashbox Test Other Company Journal", "CBXTD", company=other_company)
        other_session = self._open_session(other_journal)
        self._set_default_cashbox(other_session.cashbox_id)

        payment = (
            self.env["account.payment"]
            .with_user(self.user)
            .create({"partner_id": self.partner.id, "amount": 100.0, "date": fields.Date.today()})
        )

        self.assertFalse(payment.cashbox_session_id)
