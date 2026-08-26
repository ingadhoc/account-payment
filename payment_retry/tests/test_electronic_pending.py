from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestElectronicPending(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("payment.payment_provider_adyen").sudo()
        cls.payment_method = cls.provider.with_context(active_test=False).payment_method_ids[:1]

    def _create_invoice(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-10",
                "invoice_line_ids": [
                    (0, 0, {"name": "test", "quantity": 1, "price_unit": 1000.0, "tax_ids": []}),
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _create_transaction(self, invoice, state="pending"):
        transaction = (
            self.env["payment.transaction"]
            .sudo()
            .create(
                {
                    "provider_id": self.provider.id,
                    "payment_method_id": self.payment_method.id,
                    "partner_id": invoice.partner_id.id,
                    "amount": invoice.amount_total,
                    "currency_id": invoice.currency_id.id,
                    "reference": "test-%s" % invoice.id,
                    "operation": "online_redirect",
                    "invoice_ids": [(6, 0, invoice.ids)],
                }
            )
        )
        transaction.state = state
        invoice.invalidate_recordset()
        return transaction

    def test_01_pending_transaction_keeps_invoice_payable(self):
        """An invoice with a pending online transaction must still be payable by hand."""
        invoice = self._create_invoice()
        self._create_transaction(invoice)
        # the payment state is not overridden, so the "Pay" button and the outstanding
        # widget of the invoice form keep working
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(invoice.status_in_payment, "electronic_pending")
        self.assertTrue(invoice.has_pending_transaction)
        # but the invoice is not offered for payment on the portal, to avoid paying it twice
        self.assertFalse(invoice._has_to_be_paid())

    def test_02_register_payment_on_pending_transaction(self):
        """Registering the payment by hand while the transaction is pending pays the invoice."""
        invoice = self._create_invoice()
        self._create_transaction(invoice)
        # both entry points of the "Pay" button ask for confirmation first: the core one and the
        # one some modules bind the button to directly
        for method in ("action_register_payment", "action_force_register_payment"):
            action = getattr(invoice, method)()
            self.assertEqual(action["res_model"], "electronic.payment.pending.confirm", method)
        wizard = self.env["electronic.payment.pending.confirm"].create({"move_ids": invoice.ids})
        messages_before = len(invoice.message_ids)
        action = wizard.action_confirm()
        # confirming leaves a note in the chatter and opens the payment wizard
        self.assertEqual(action["res_model"], "account.payment.register")
        self.assertEqual(len(invoice.message_ids), messages_before + 1)
        self.env["account.payment.register"].with_context(active_model="account.move", active_ids=invoice.ids).create(
            {}
        ).action_create_payments()
        invoice.invalidate_recordset()
        # 'in_payment' when the payment journal has an outstanding account set, 'paid' otherwise
        self.assertIn(invoice.payment_state, ("paid", "in_payment"))
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_03_authorized_transaction(self):
        """An authorized transaction is also considered on course."""
        invoice = self._create_invoice()
        transaction = self._create_transaction(invoice)
        # bypass the ORM: the demo providers do not support manual capture
        self.env.cr.execute("UPDATE payment_transaction SET state = 'authorized' WHERE id = %s", (transaction.id,))
        transaction.invalidate_recordset()
        invoice.invalidate_recordset()
        self.assertTrue(invoice.has_pending_transaction)
        self.assertEqual(invoice.status_in_payment, "electronic_pending")
        self.assertFalse(invoice._has_to_be_paid())

    def test_04_cancelled_transaction_releases_the_invoice(self):
        """A cancelled or expired transaction leaves no trace on the invoice."""
        invoice = self._create_invoice()
        transaction = self._create_transaction(invoice)
        transaction.state = "cancel"
        invoice.invalidate_recordset()
        self.assertFalse(invoice.has_pending_transaction)
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertNotEqual(invoice.status_in_payment, "electronic_pending")
        self.assertTrue(invoice._has_to_be_paid())

    def test_05_no_warning_without_pending_transaction(self):
        """Without an electronic payment on course, the "Pay" button goes straight to the wizard."""
        invoice = self._create_invoice()
        for method in ("action_register_payment", "action_force_register_payment"):
            action = getattr(invoice, method)()
            self.assertEqual(action["res_model"], "account.payment.register", method)
