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

    # TODO revisar por qué al cambiar por shell los valores se vuelve a cambiar el nombre
    # def test_payment_sequence_with_reset_to_draft(self):
    #     """Test payment sequence behavior when resetting to draft and reposting."""
    #     self.company = self.env.ref('base.company_ri')
    #     # Step 1: Create a payment with an amount of 100 and post it
    #     receiptbook_id = self.env["account.payment.receiptbook"].search(
    #         [("company_id", "=", self.company.id), ("name", "=", "Customer Receipts")]
    #     )
    #     payment_vals = {
    #         "journal_id": self.company_bank_journal.id,
    #         "amount": 100,
    #         "date": self.today,
    #         "receiptbook_id": receiptbook_id.id
    #     }
    #     payment = self.env["account.payment"].create(payment_vals)
    #     payment.action_post()

    #     # Step 2: Reset the payment to draft
    #     payment.action_draft()

    #     # Step 3: Change amount
    #     payment.write({'amount': 123})

    #     # Step 4: Post the payment again
    #     payment.action_post()

    #     # Assert the payment name is updated to the next expected name in the receiptbook sequence
    #     new_number_next_actual = receiptbook_id.with_context(ir_sequence_date=self.today).sequence_id.number_next_actual
    #     new_expected_name = "%s %s%s" % (
    #         receiptbook_id.document_type_id.doc_code_prefix,
    #         receiptbook_id.prefix,
    #         str(new_number_next_actual).zfill(receiptbook_id.sequence_id.padding),
    #     )
    #     self.assertEqual(payment.name, new_expected_name,
    #                      "The payment sequence did not update to the next expected name after resetting to draft.")
