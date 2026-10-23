from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.addons.account_payment.tests.common import AccountPaymentCommon
from odoo.addons.account_payment_ux.controllers.portal import PortalAccountInherit
from odoo.addons.http_routing.tests.common import MockRequest
from odoo.tests import tagged


@tagged("-at_install", "post_install")
class TestAccountPaymentUx(AccountPaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.env["ir.config_parameter"].sudo().set_param("account_payment.enable_portal_payment", True)

    def _create_posted_invoice(self, **values):
        invoice = self.init_invoice("out_invoice", partner=self.partner, amounts=[1000.0], currency=self.currency)
        invoice.write(values)
        invoice.action_post()
        return invoice

    def _overdue_invoices(self, partner):
        with MockRequest(self.env):
            domain = PortalAccountInherit()._get_overdue_invoices_domain(partner_id=partner.id)
        return self.env["account.move"].search(domain)

    def test_pending_transaction_blocks_online_payment(self):
        """Given an overdue customer invoice, a pending transaction of any provider
        hides "Pay now" and removes the invoice from the portal overdue invoices.

        The dummy provider has code 'none', which the core does not block: the
        block measured here is the one of this module.
        """
        invoice = self._create_posted_invoice(invoice_date_due=self.today - relativedelta(days=10))

        with self.subTest("without a pending transaction, the invoice can be paid and is overdue"):
            self.assertTrue(invoice._has_to_be_paid())
            self.assertIn(invoice, self._overdue_invoices(invoice.partner_id))

        self._create_transaction(
            "redirect", state="pending", amount=invoice.amount_total, invoice_ids=[(6, 0, invoice.ids)]
        )
        invoice.invalidate_recordset(["transaction_ids"])

        with self.subTest("with a pending transaction, the invoice cannot be paid and is not overdue"):
            self.assertFalse(invoice._has_to_be_paid())
            self.assertNotIn(invoice, self._overdue_invoices(invoice.partner_id))

    def test_post_process_posts_and_reconciles_draft_payment(self):
        """Given a done transaction whose payment went back to draft, the post-process
        posts the payment and reconciles it with the invoice, but only when the
        payment keeps the amount and currency of the transaction.
        """
        for label, amount_delta, expect_posted in (
            ("with the same amount, the payment is posted and the invoice is paid", 0.0, True),
            ("with another amount, the payment stays in draft", 1.0, False),
        ):
            with self.subTest(label):
                invoice = self._create_posted_invoice()
                tx = self._create_transaction(
                    "redirect",
                    state="done",
                    amount=invoice.amount_total,
                    reference=f"TX-{invoice.id}",
                    invoice_ids=[(6, 0, invoice.ids)],
                )
                tx._post_process()
                payment = tx.payment_id
                payment.action_draft()
                payment.amount += amount_delta
                tx.is_post_processed = False

                tx._post_process()

                self.assertEqual(tx.payment_id, payment, "The post-process must not create another payment")
                if expect_posted:
                    self.assertEqual(payment.move_id.state, "posted")
                    self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
                else:
                    self.assertEqual(payment.state, "draft")
                    self.assertEqual(invoice.amount_residual, invoice.amount_total)
