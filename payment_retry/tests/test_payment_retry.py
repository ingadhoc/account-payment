from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPaymentRetry(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("payment.payment_provider_adyen").sudo()
        cls.payment_method = (
            cls.env["payment.method"]
            .sudo()
            .create({"name": "Test", "code": "test_payment_retry_cron", "provider_id": cls.provider.id})
        )
        cls.invoice = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2026-08-10",
                "invoice_line_ids": [
                    (0, 0, {"name": "test", "quantity": 1, "price_unit": 1000.0, "tax_ids": []}),
                ],
            }
        )
        cls.invoice.action_post()

    def _create_transaction(self, reference, asynchronous_process=True):
        return (
            self.env["payment.transaction"]
            .sudo()
            .create(
                {
                    "provider_id": self.provider.id,
                    "payment_method_id": self.payment_method.id,
                    "partner_id": self.invoice.partner_id.id,
                    "amount": self.invoice.amount_total,
                    "currency_id": self.invoice.currency_id.id,
                    "reference": reference,
                    "operation": "offline",
                    "invoice_ids": [(6, 0, self.invoice.ids)],
                    "asynchronous_process": asynchronous_process,
                }
            )
        )

    def _run_async_cron(self, send_payment_request):
        """Run the asynchronous cron as the cron user would, without committing: the test cursor
        does not allow it."""
        with (
            patch.object(type(self.env["payment.transaction"]), "_send_payment_request", send_payment_request),
            patch.object(type(self.env["ir.cron"]), "_commit_progress", lambda *args, **kwargs: float("inf")),
            patch.object(self.env.cr, "rollback", lambda: None),
        ):
            self.env["payment.transaction"].sudo().cron_asynchronous_process()

    def test_01_cron_does_not_resend_a_transaction_already_sent(self):
        """A draft transaction whose provider answer waits in payment.data is not sent again."""
        to_send = self._create_transaction("retry-to-send")
        processing = self._create_transaction("retry-processing")
        failed = self._create_transaction("retry-failed")
        self.env["payment.data"].sudo().create({"transaction_id": processing.id, "payload": {"ok": True}})
        self.env["payment.data"].sudo().create({"transaction_id": failed.id, "payload": {"ok": False}, "errored": True})
        sent = self.env["payment.transaction"]

        def send_payment_request(tx):
            nonlocal sent
            sent |= tx

        self._run_async_cron(send_payment_request)
        self.assertEqual(sent & (to_send | processing | failed), to_send)

    def test_02_cron_sets_error_when_the_request_fails(self):
        """A failed request leaves the transaction in error."""
        tx = self._create_transaction("retry-error")

        def send_payment_request(tx):
            raise Exception("request failed")

        with self.assertLogs("odoo.addons.payment_retry.models.payment_transaction", level="ERROR") as logs:
            self._run_async_cron(send_payment_request)
        self.assertEqual(tx.state, "error")
        self.assertIn("request failed", logs.output[0])

    def test_03_post_processing_skips_transactions_waiting_to_be_sent(self):
        """The post-processing leaves out the asynchronous transactions still in draft."""
        waiting = self._create_transaction("retry-waiting")
        regular = self._create_transaction("retry-regular", asynchronous_process=False)
        (waiting | regular).with_context(payment_safe_write=True).write({"is_post_processed": False})
        (waiting | regular)._post_process_with_lock()
        self.assertFalse(waiting.is_post_processed)
        self.assertTrue(regular.is_post_processed)

    def test_04_sent_transaction_keeps_the_invoice_on_course(self):
        """While the provider answer waits to be processed, the invoice counts as being paid."""
        tx = self._create_transaction("retry-on-course", asynchronous_process=False)
        self.invoice.invalidate_recordset()
        self.assertFalse(self.invoice.has_pending_transaction)
        self.env["payment.data"].sudo().create({"transaction_id": tx.id, "payload": {"ok": True}})
        self.invoice.invalidate_recordset()
        self.assertTrue(self.invoice.has_pending_transaction)
        self.assertEqual(self.invoice.status_in_payment, "electronic_pending")
        self.assertFalse(self.invoice._has_to_be_paid())
        # nor is it offered again in the retry wizard
        wizard_values = (
            self.env["payment.transaction.retry"]
            .with_context(active_model="account.move", active_ids=self.invoice.ids)
            .default_get(["line_ids"])
        )
        self.assertFalse(wizard_values["line_ids"])
