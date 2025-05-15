import json

import odoo.tests.common as common
from odoo import Command, fields
from odoo.exceptions import ValidationError


class TestAccountPaymentProReceiptbookUnitTest(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.company = self.env.company
        self.company_bank_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "bank")], limit=1
        )
        self.company_sale_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "sale")], limit=1
        )
        self.company.use_payment_pro = True
        self.company.use_receiptbook = True
        self.partner_ri = self.env["res.partner"].search([("name", "=", "Deco Addict")])
        self.receiptbook = self.env["account.payment.receiptbook"].search(
            [("company_id", "=", self.company.id), ("name", "=", "Customer Receipts")]
        )

    def test_create_payment_with_receiptbook(self):
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "out_invoice",
                "journal_id": self.company_sale_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 100,
                        }
                    ),
                ],
            }
        )
        invoice.action_post()
        receiptbook_id = self.env["account.payment.receiptbook"].search(
            [("company_id", "=", self.company.id), ("name", "=", "Customer Receipts")]
        )
        number_next_actual = receiptbook_id.with_context(ir_sequence_date=self.today).sequence_id.number_next_actual
        name = "%s %s%s" % (
            receiptbook_id.document_type_id.doc_code_prefix,
            receiptbook_id.prefix,
            str(number_next_actual).zfill(receiptbook_id.sequence_id.padding),
        )

        vals = {
            "journal_id": self.company_bank_journal.id,
            "amount": invoice.amount_total,
            "date": self.today,
        }
        action_context = invoice.action_register_payment()["context"]
        payment = self.env["account.payment"].with_context(**action_context).create(vals)
        payment.action_post()
        self.assertEqual(payment.name, name, "no se tomo la secuencia correcta del pago")

    def test_payment_amount_update(self):
        """Test creating a payment, posting it, resetting to draft, updating amount, and validating name."""
        payment = self.env["account.payment"].create(
            {
                "amount": 100,
                "payment_type": "inbound",
                "partner_id": self.env.ref("l10n_ar.res_partner_adhoc").id,
                "journal_id": self.company_bank_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": self.receiptbook.id,
            }
        )

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
        self.assertEqual(
            payment.name, original_name, "The payment name should remain the same after updating the amount."
        )

    def test_payment_name_uniqueness(self):
        """
        Create 2 payments with bank and cash journals, post them,
        try to resequence the first one with the name of the second and validate ValidationError.
        """
        # Search for cash journal
        cash_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "cash")], limit=1
        )
        self.assertTrue(self.company_bank_journal, "No bank journal found")
        self.assertTrue(cash_journal, "No cash journal found")

        # Create first payment (bank)
        payment1 = self.env["account.payment"].create(
            {
                "amount": 100,
                "payment_type": "inbound",
                "partner_id": self.partner_ri.id,
                "journal_id": self.company_bank_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": self.receiptbook.id,
            }
        )
        payment1.action_post()

        # Create second payment (cash)
        payment2 = self.env["account.payment"].create(
            {
                "amount": 200,
                "payment_type": "inbound",
                "partner_id": self.partner_ri.id,
                "journal_id": cash_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": self.receiptbook.id,
            }
        )
        payment2.action_post()

        # Try to resequence the first payment with the name of the second
        resequence_wizard = self.env["account.resequence.wizard"].create(
            {
                "move_ids": [(6, 0, [payment1.move_id.id])],
                "ordering": "keep",
                "new_values": json.dumps(
                    {
                        str(payment1.move_id.id): {
                            "new_by_name": payment2.name,
                            "new_by_date": payment2.name,
                        }
                    }
                ),
                "first_name": payment2.name,
            }
        )
        with self.assertRaises(ValidationError) as cm:
            resequence_wizard.resequence()
        self.assertIn("already exist", str(cm.exception))
