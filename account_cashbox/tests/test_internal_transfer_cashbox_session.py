from odoo import Command, fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestInternalTransferCashboxSession(common.TransactionCase):
    """Tests para validar transferencias internas con sesiones de caja"""

    def setUp(self):
        super().setUp()
        self.company = self.env.company

        # Buscar journals existentes con outstanding account configurado
        journals = self.env["account.journal"].search(
            [
                ("company_id", "=", self.company.id),
                ("type", "in", ["bank", "cash"]),
                ("default_account_id", "!=", False),
            ],
            limit=2,
        )

        if len(journals) < 2:
            # Si no hay journals con outstanding account, buscar cualquiera y configurarlo
            journals = self.env["account.journal"].search(
                [("company_id", "=", self.company.id), ("type", "in", ["bank", "cash"])], limit=2
            )

            if len(journals) < 2:
                self.skipTest("Se requieren al menos 2 journals de tipo bank/cash para ejecutar este test")

            # Configurar outstanding account si no existe
            for journal in journals:
                if not journal.default_account_id:
                    # Buscar o crear una cuenta de outstanding
                    outstanding_account = self.env["account.account"].search(
                        [
                            ("company_id", "=", self.company.id),
                            ("account_type", "=", "asset_current"),
                            ("reconcile", "=", True),
                        ],
                        limit=1,
                    )
                    if outstanding_account:
                        journal.default_account_id = outstanding_account

        self.source_journal = journals[0]
        self.destination_journal = journals[1]

        # Configurar payment method lines con payment_account_id
        for journal in [self.source_journal, self.destination_journal]:
            for line in journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids:
                if not line.payment_account_id and journal.default_account_id:
                    line.payment_account_id = journal.default_account_id

        # Crear cashboxes (cajas) para las sesiones con allow_concurrent_sessions
        self.source_cashbox = self.env["account.cashbox"].create(
            {
                "name": "Source Cashbox",
                "company_id": self.company.id,
                "journal_ids": [Command.link(self.source_journal.id)],
                "allow_concurrent_sessions": True,
            }
        )

        self.destination_cashbox = self.env["account.cashbox"].create(
            {
                "name": "Destination Cashbox",
                "company_id": self.company.id,
                "journal_ids": [Command.link(self.destination_journal.id)],
                "allow_concurrent_sessions": True,
            }
        )

        # Crear y abrir sesiones de caja
        self.source_session = self.env["account.cashbox.session"].create(
            {
                "cashbox_id": self.source_cashbox.id,
                "name": "Source Session 001",
            }
        )
        self.source_session.action_account_cashbox_session_open()

        self.destination_session = self.env["account.cashbox.session"].create(
            {
                "cashbox_id": self.destination_cashbox.id,
                "name": "Destination Session 001",
            }
        )
        self.destination_session.action_account_cashbox_session_open()

    def test_internal_transfer_sets_destination_cashbox_session(self):
        """Verifica que al crear una transferencia interna con destination_cashbox_session_id,
        el pago pareado obtiene la sesión de caja destino correcta"""

        # Crear un pago de transferencia interna con sesión de caja origen y destino
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.source_journal.id,
                "destination_journal_id": self.destination_journal.id,
                "amount": 1000.0,
                "date": fields.Date.today(),
                "cashbox_session_id": self.source_session.id,
                "destination_cashbox_session_id": self.destination_session.id,
                "is_internal_transfer": True,
            }
        )

        # Postear el pago (esto debería crear el pago pareado)
        payment.action_post()

        # Verificar que existe el pago pareado
        self.assertTrue(
            payment.paired_internal_transfer_payment_id, "El pago pareado de transferencia interna no fue creado"
        )

        # Verificar que el pago pareado tiene la sesión de caja destino
        paired_payment = payment.paired_internal_transfer_payment_id
        self.assertEqual(
            paired_payment.cashbox_session_id,
            self.destination_session,
            "El pago pareado no tiene la sesión de caja destino correcta",
        )

        # Verificar que el campo destination_cashbox_session_id del pago pareado es False
        self.assertFalse(
            paired_payment.destination_cashbox_session_id,
            "El destination_cashbox_session_id del pago pareado debería ser False",
        )

    def test_internal_transfer_without_destination_session(self):
        """Verifica que cuando no se especifica destination_cashbox_session_id,
        el pago pareado se crea sin sesión de caja"""

        # Crear un pago de transferencia interna sin destination_cashbox_session_id
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.source_journal.id,
                "destination_journal_id": self.destination_journal.id,
                "amount": 500.0,
                "date": fields.Date.today(),
                "cashbox_session_id": self.source_session.id,
                "is_internal_transfer": True,
            }
        )

        # Postear el pago
        payment.action_post()

        # Verificar que existe el pago pareado
        self.assertTrue(
            payment.paired_internal_transfer_payment_id, "El pago pareado de transferencia interna no fue creado"
        )

        # Verificar que el pago pareado no tiene sesión de caja
        paired_payment = payment.paired_internal_transfer_payment_id
        self.assertFalse(
            paired_payment.cashbox_session_id,
            "El pago pareado no debería tener sesión de caja cuando no se especifica destination_cashbox_session_id",
        )

    def test_multiple_internal_transfers_with_sessions(self):
        """Verifica que múltiples transferencias internas con sesiones de caja
        funcionan correctamente"""

        payments = self.env["account.payment"]

        # Crear múltiples pagos
        for i in range(3):
            payment = self.env["account.payment"].create(
                {
                    "journal_id": self.source_journal.id,
                    "destination_journal_id": self.destination_journal.id,
                    "amount": 100.0 * (i + 1),
                    "date": fields.Date.today(),
                    "cashbox_session_id": self.source_session.id,
                    "destination_cashbox_session_id": self.destination_session.id,
                    "is_internal_transfer": True,
                }
            )
            payments |= payment

        # Postear todos los pagos
        payments.action_post()

        # Verificar que todos los pagos pareados tienen la sesión correcta
        for payment in payments:
            self.assertTrue(
                payment.paired_internal_transfer_payment_id, f"El pago pareado para el pago {payment.id} no fue creado"
            )
            self.assertEqual(
                payment.paired_internal_transfer_payment_id.cashbox_session_id,
                self.destination_session,
                f"El pago pareado del pago {payment.id} no tiene la sesión de caja destino correcta",
            )
            self.assertFalse(
                payment.paired_internal_transfer_payment_id.destination_cashbox_session_id,
                f"El destination_cashbox_session_id del pago pareado {payment.id} debería ser False",
            )

    def test_destination_session_domain_filter(self):
        """Verifica que solo sesiones abiertas pueden ser seleccionadas como destino"""

        # Crear una tercera sesión pero cerrada
        closed_cashbox = self.env["account.cashbox"].create(
            {
                "name": "Closed Cashbox",
                "company_id": self.company.id,
                "journal_ids": [Command.link(self.destination_journal.id)],
                "allow_concurrent_sessions": True,
            }
        )

        closed_session = self.env["account.cashbox.session"].create(
            {
                "cashbox_id": closed_cashbox.id,
                "name": "Closed Session 001",
            }
        )
        closed_session.action_account_cashbox_session_open()
        closed_session.action_closing_control()
        closed_session.action_account_cashbox_session_close()

        # Crear pago en la primera compañía
        # Solo debería poder usar sesiones abiertas en destination_cashbox_session_id
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.source_journal.id,
                "destination_journal_id": self.destination_journal.id,
                "amount": 1000.0,
                "date": fields.Date.today(),
                "cashbox_session_id": self.source_session.id,
                "destination_cashbox_session_id": self.destination_session.id,
                "is_internal_transfer": True,
            }
        )

        # Verificar que la sesión destino es la abierta
        self.assertEqual(payment.destination_cashbox_session_id, self.destination_session)
        self.assertNotEqual(payment.destination_cashbox_session_id, closed_session)
