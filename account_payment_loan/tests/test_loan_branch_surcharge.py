from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestLoanBranchSurcharge(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.company_data["company"]
        cls.branch = cls.env["res.company"].create(
            {"name": "Branch", "parent_id": cls.parent.id, "country_id": cls.parent.country_id.id}
        )
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=(cls.branch + cls.parent).ids))
        cls.branch.loan_journal_id = cls.parent.loan_journal_id
        cls.branch_sale_journal = cls.env["account.journal"].create(
            {
                "name": "Branch Sales",
                "type": "sale",
                "code": "BRSAL",
                "company_id": cls.branch.id,
                "default_account_id": cls.company_data["default_account_revenue"].id,
            }
        )
        # the branch is created after the chart was loaded, so it gets no default accounts
        cls.partner_a.with_company(cls.branch).property_account_receivable_id = cls.company_data[
            "default_account_receivable"
        ]

        # the surcharge product only carries the sales tax of the parent company
        cls.surcharge_product = cls.env["product.product"].create(
            {"name": "Financial Surcharge", "type": "service", "taxes_id": [Command.set(cls.tax_sale_a.ids)]}
        )
        cls.surcharge_product.with_company(cls.branch).property_account_income_id = cls.company_data[
            "default_account_revenue"
        ]
        cls.branch.product_surcharge_id = cls.surcharge_product

        cls.card = cls.env["account.card"].create(
            {
                "name": "Loans",
                "is_loan": True,
                "loan_due_method": "create_day",
                "installment_ids": [
                    Command.create({"name": "3", "divisor": 3, "surcharge_coefficient": 1.2}),
                ],
            }
        )

    def test_branch_loan_surcharge_uses_parent_tax(self):
        """A branch without its own sales tax invoices the loan surcharge with the tax of its parent company."""
        invoice = (
            self.env["account.move"]
            .with_company(self.branch)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "journal_id": self.branch_sale_journal.id,
                    "invoice_line_ids": [
                        Command.create({"name": "test", "quantity": 1, "price_unit": 1000.0, "tax_ids": []}),
                    ],
                }
            )
        )
        invoice.action_post()
        receivable = invoice.line_ids.filtered(lambda x: x.account_id.account_type == "asset_receivable")
        wizard = (
            self.env["account.loan.register"]
            .with_context(active_ids=receivable.ids)
            .create({"card_id": self.card.id, "installment_id": self.card.installment_ids.id, "is_invoiceable": True})
        )
        self.assertEqual(wizard.company_id, self.branch)

        wizard.action_register_loan()

        debit_note = invoice.debit_note_ids
        self.assertEqual(debit_note.state, "posted")
        surcharge_line = debit_note.invoice_line_ids.filtered(lambda line: line.product_id == self.surcharge_product)
        self.assertEqual(surcharge_line.tax_ids, self.tax_sale_a)
        self.assertAlmostEqual(debit_note.amount_total, 200.0, places=2)
