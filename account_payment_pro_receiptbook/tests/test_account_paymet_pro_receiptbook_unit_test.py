import odoo.tests.common as common
from odoo import Command, fields


class TestAccountPaymentProReceiptbookUnitTest(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.company = self.env.ref('l10n_ar.company_ri')
        self.company_bank_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "bank")], limit=1
        )
        self.company_sale_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "sale")], limit=1
        )
        self.receiptbook = self.env["account.payment.receiptbook"].search(
            [("company_id", "=", self.company.id), ("name", "=", "Customer Receipts")]
        )

    def test_payment_amount_update(self):
        """Test creating a payment, posting it, resetting to draft, updating amount, and validating name."""
        payment = self.env["account.payment"].create({
            "amount": 100,
            "payment_type": "inbound",
            "partner_id": self.env.ref("l10n_ar.res_partner_adhoc").id,
            "journal_id": self.company_bank_journal.id,
            "date": self.today,
            "company_id": self.company.id,
            "receiptbook_id": self.receiptbook.id
        })

        # Post the payment
        payment.action_post()
        original_name = payment.name

        # Reset to draft
        payment.action_draft()

        # Update the amount
        payment.amount = 200

        # Post again
        payment.action_post()

        # Validate that the name remains the same
        self.assertEqual(payment.name, original_name, "The payment name should remain the same after updating the amount.")
