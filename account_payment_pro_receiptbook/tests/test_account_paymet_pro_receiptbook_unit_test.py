import odoo.tests.common as common
from odoo import Command, fields


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
