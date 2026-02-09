import json

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestAccountPaymentProReceiptbookUnitTest(TransactionCase):
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
        # Create a test partner instead of relying on demo data
        self.partner_ri = self.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "test@example.com",
                "is_company": True,
            }
        )
        self.receiptbook = self.env["account.payment.receiptbook"].search(
            [("company_id", "=", self.company.id), ("name", "=", "Customer Receipts")]
        )
        # Create a simple product for testing instead of relying on external ID
        self.test_product = self.env["product.product"].create(
            {
                "name": "Test Product",
                "list_price": 100.0,
                "type": "service",
            }
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
                            "product_id": self.test_product.id,
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
                "partner_id": self.partner_ri.id,
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
        if cash_journal:
            (cash_journal.outbound_payment_method_line_ids + cash_journal.inbound_payment_method_line_ids).write(
                {"payment_account_id": cash_journal.default_account_id.id}
            )

        (
            self.company_bank_journal.outbound_payment_method_line_ids
            + self.company_bank_journal.inbound_payment_method_line_ids
        ).write({"payment_account_id": self.company_bank_journal.default_account_id.id})

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
        payment1.filtered(lambda p: not p.move_id)._generate_journal_entry()

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
        payment2.filtered(lambda p: not p.move_id)._generate_journal_entry()

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

    def test_payment_register_keeps_receiptbook_sequence(self):
        """
        Test the specific use case:
        1. Create a payment with receiptbook (to advance the sequence)
        2. Create 2 invoices
        3. Use payment register wizard to pay both invoices
        4. Verify payment names follow receiptbook sequence, not Odoo numbering

        This validates the fix where _compute_name should not recompute names
        for posted payments with receiptbook.
        """
        # Step 1: Create an initial payment with receiptbook to advance the sequence
        # We need a vendor receiptbook for outbound payments
        vendor_receiptbook = self.env["account.payment.receiptbook"].search(
            [("partner_type", "=", "supplier"), ("company_id", "=", self.company.id)], limit=1
        )
        if not vendor_receiptbook:
            # Create a vendor receiptbook if it doesn't exist
            vendor_receiptbook = self.env["account.payment.receiptbook"].create(
                {
                    "name": "Vendor Payments",
                    "partner_type": "supplier",
                    "company_id": self.company.id,
                    "sequence_id": self.env["ir.sequence"]
                    .create(
                        {
                            "name": "Vendor Payment Sequence",
                            "code": "vendor.payment",
                            "prefix": "OP-X 0001-",
                            "padding": 8,
                        }
                    )
                    .id,
                    "document_type_id": self.env["l10n_latam.document.type"]
                    .search(
                        [
                            ("code", "=", "112")  # Recibo code
                        ],
                        limit=1,
                    )
                    .id,
                }
            )

        initial_payment = self.env["account.payment"].create(
            {
                "amount": 50,
                "payment_type": "outbound",
                "partner_id": self.partner_ri.id,
                "journal_id": self.company_bank_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": vendor_receiptbook.id,
            }
        )
        initial_payment.action_post()

        # Get the next expected receiptbook numbers
        receiptbook_sequence = vendor_receiptbook.sequence_id
        next_number_after_initial = receiptbook_sequence.number_next_actual

        # Step 2: Create 2 vendor invoices
        invoice1 = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "in_invoice",
                "journal_id": self.env["account.journal"]
                .search([("company_id", "=", self.company.id), ("type", "=", "purchase")], limit=1)
                .id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.test_product.id,
                            "quantity": 1,
                            "price_unit": 100,
                        }
                    ),
                ],
            }
        )

        invoice2 = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "in_invoice",
                "journal_id": self.env["account.journal"]
                .search([("company_id", "=", self.company.id), ("type", "=", "purchase")], limit=1)
                .id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.test_product.id,
                            "quantity": 1,
                            "price_unit": 200,
                        }
                    ),
                ],
            }
        )

        invoice1.action_post()
        invoice2.action_post()

        # Step 3: Use payment register wizard to pay both invoices
        payment_register = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=[invoice1.id, invoice2.id])
            .create(
                {
                    "journal_id": self.company_bank_journal.id,
                    "group_payment": False,  # Create separate payments for each invoice
                }
            )
        )

        # Process the payment register
        action = payment_register.action_create_payments()
        payment_ids = action["domain"][0][2] if action.get("domain") else []
        created_payments = self.env["account.payment"].browse(payment_ids)

        # Step 4: Verify payment names follow receiptbook sequence
        self.assertEqual(len(created_payments), 2, "Should create 2 separate payments")

        # Sort payments by id to have consistent order
        payments_sorted = created_payments.sorted("id")

        # Build expected receiptbook names
        expected_names = []
        for i in range(2):
            expected_number = next_number_after_initial + i
            expected_name = "%s %s%s" % (
                vendor_receiptbook.document_type_id.doc_code_prefix,
                vendor_receiptbook.prefix,
                str(expected_number).zfill(vendor_receiptbook.sequence_id.padding),
            )
            expected_names.append(expected_name)

        # Verify each payment has the correct receiptbook name
        for payment, expected_name in zip(payments_sorted, expected_names):
            self.assertEqual(
                payment.name,
                expected_name,
                f"Payment {payment.id} should have receiptbook name {expected_name}, got {payment.name}",
            )

            # Trigger _compute_name to ensure the fix works
            payment._compute_name()

            # Verify name is still preserved after _compute_name
            self.assertEqual(
                payment.name,
                expected_name,
                f"Payment {payment.id} should preserve receiptbook name {expected_name} after _compute_name, got {payment.name}",
            )
