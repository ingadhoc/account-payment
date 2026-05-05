import json

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError


class TestAccountPaymentProReceiptbookUnitTest(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def get_default_groups(cls):
        groups = super().get_default_groups()
        product_mgmt_group = cls.env.ref(
            "product_management_group.group_products_management",
            raise_if_not_found=False,
        )
        if product_mgmt_group:
            groups |= product_mgmt_group
        return groups

    @classmethod
    def setup_armageddon_tax(cls, tax_name, company_data, **kwargs):
        # Ensure a tax group exists for the company's fiscal country so that
        # _compute_tax_group_id (which searches without sudo) can find one.
        # This is necessary when running at_install tests against a localised
        # company where country/fiscal-country state becomes inconsistent during
        # AccountTestInvoicingCommon.setup_independent_company.
        company = company_data["company"]
        fiscal_country = company.account_fiscal_country_id or company.country_id
        TaxGroup = cls.env["account.tax.group"].sudo()
        for country_id in ([fiscal_country.id] if fiscal_country else []) + [False]:
            if not TaxGroup.search(
                [
                    ("company_id", "parent_of", company.ids),
                    ("country_id", "=", country_id),
                ],
                limit=1,
            ):
                TaxGroup.create(
                    {
                        "name": "Test Tax Group",
                        "company_id": company.id,
                        "country_id": country_id,
                    }
                )
        return super().setup_armageddon_tax(tax_name, company_data, **kwargs)

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
        ar = self.env.ref("base.ar")
        self.partner_ri = self.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))
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
        name = "%s %s%s" % (
            receiptbook_id.document_type_id.doc_code_prefix,
            receiptbook_id.prefix,
            str(1).zfill(8),
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
                "partner_id": self.partner_a.id,
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
            payment.name,
            original_name,
            "The payment name should remain the same after updating the amount.",
        )

    def test_payment_name_uniqueness(self):
        """
        Create 2 payments with bank and cash journals, post them,
        try to resequence the first one with the name of the second and validate ValidationError.
        """
        # Search for cash journal (fallback to searching/creating if company_data entry is missing)
        cash_journal = False
        try:
            cash_journal = self.company_data.get("default_journal_cash")
        except Exception:
            cash_journal = False
        if not cash_journal:
            cash_journal = self.env["account.journal"].search(
                [("company_id", "=", self.company.id), ("type", "=", "cash")], limit=1
            )
        if not cash_journal:
            cash_journal = self.env["account.journal"].create(
                {"type": "cash", "name": "Cash", "company_id": self.company.id}
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
