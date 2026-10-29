from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestFinancialSurchargeBranch(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.company_data["company"]
        cls.branch = cls.env["res.company"].create(
            {"name": "Branch", "parent_id": cls.parent.id, "country_id": cls.parent.country_id.id}
        )
        cls.cr.precommit.run()  # load the CoA on the branch
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=(cls.branch + cls.parent).ids))
        cls.branch_sale_journal = cls.env["account.journal"].create(
            {
                "name": "Branch Sales",
                "type": "sale",
                "code": "BRSAL",
                "company_id": cls.branch.id,
                "default_account_id": cls.company_data["default_account_revenue"].id,
            }
        )
        cls.branch_bank_journal = cls.env["account.journal"].create(
            {"name": "Branch Bank", "type": "bank", "code": "BRBNK", "company_id": cls.branch.id}
        )

        # the surcharge product only carries the sales tax of the parent company
        cls.surcharge_product = cls.env["product.product"].create(
            {"name": "Financial Surcharge", "type": "service", "taxes_id": [Command.set(cls.tax_sale_a.ids)]}
        )
        cls.branch.product_surcharge_id = cls.surcharge_product

        cls.card = cls.env["account.card"].create({"name": "Test Card", "company_id": cls.parent.id})
        cls.installment = cls.env["account.card.installment"].create(
            {"card_id": cls.card.id, "name": "3", "divisor": 3, "installment": 3, "surcharge_coefficient": 1.10}
        )
        cls.method_line = cls.branch_bank_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "manual"
        )
        cls.method_line.available_card_ids = cls.card

    def test_branch_surcharge_uses_parent_tax(self):
        """A branch without its own sales tax invoices the surcharge with the tax of its parent company."""
        payment = (
            self.env["account.payment"]
            .with_company(self.branch)
            .create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner_a.id,
                    "journal_id": self.branch_bank_journal.id,
                    "payment_method_line_id": self.method_line.id,
                    "card_id": self.card.id,
                    "installment_id": self.installment.id,
                    "amount": 110_000,
                }
            )
        )
        self.assertAlmostEqual(payment.financing_surcharge, 10_000, places=2)

        payment.action_post()

        debit_note = self.env["account.move"].search(
            [("company_id", "=", self.branch.id), ("invoice_line_ids.product_id", "=", self.surcharge_product.id)]
        )
        self.assertEqual(debit_note.state, "posted")
        self.assertEqual(debit_note.journal_id, self.branch_sale_journal)
        self.assertEqual(debit_note.invoice_line_ids.tax_ids, self.tax_sale_a)
        self.assertAlmostEqual(debit_note.amount_total, 10_000, places=2)
