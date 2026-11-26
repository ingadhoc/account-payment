from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCashboxAllowedUsersViewPayments(TransactionCase):
    """
    Valida que los usuarios en allowed_users_view_payments pueden ver sesiones y pagos,
    pero no operar la caja (no pueden abrir/cerrar ni crear movimientos).
    Reutiliza datos demo.
    """

    def setUp(self):
        super().setUp()
        self.env = self.env(context=dict(self.env.context, no_reset_password=True))
        self.cashbox_model = self.env["account.cashbox"]
        self.session_model = self.env["account.cashbox.session"]
        self.payment_model = self.env["account.payment"]

        # Usuario demo (de cashbox_demo.xml)
        self.user_viewer = self.env.ref("account_cashbox.user_demo_invoicing")

        # Caja demo (de cashbox_demo.xml), le asignamos el usuario viewer en allowed_users_view_payments
        self.cashbox = self.env.ref("account_cashbox.pop_config_caja_1")
        self.cashbox.allowed_users_view_payments = [(6, 0, [self.user_viewer.id])]

        # Buscar o crear una sesión para la caja demo
        session = self.session_model.search(
            [
                ("cashbox_id", "=", self.cashbox.id),
            ],
            limit=1,
        )
        if not session:
            session = self.session_model.create(
                {
                    "cashbox_id": self.cashbox.id,
                    "user_ids": [(6, 0, [self.env.user.id])],
                }
            )
        self.session = session

        # Buscar o crear un payment asociado a la caja demo
        journal = (
            self.cashbox.journal_ids
            and self.cashbox.journal_ids[0]
            or self.env["account.journal"].search([("type", "=", "cash")], limit=1)
        )
        payment = self.payment_model.search(
            [
                ("journal_id", "=", journal.id),
                ("amount", ">", 0),
            ],
            limit=1,
        )
        if not payment:
            payment = self.payment_model.create(
                {
                    "amount": 100,
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.env.ref("base.res_partner_1").id,
                    "journal_id": journal.id,
                }
            )
        self.payment = payment

    def test_viewer_can_see_sessions_and_payments(self):
        sessions = self.session_model.with_user(self.user_viewer).search([("cashbox_id", "=", self.cashbox.id)])
        payments = self.payment_model.with_user(self.user_viewer).search(
            [("journal_id", "in", self.cashbox.journal_ids.ids)]
        )
        self.assertTrue(sessions, "Viewer should see sessions")
        self.assertTrue(payments, "Viewer should see payments")
