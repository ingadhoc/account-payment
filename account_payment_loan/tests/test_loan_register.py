from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLoanRegister(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.loan_terms = "<p>Company terms</p>"
        cls.card = cls.env["account.card"].create(
            {
                "name": "Loan card",
                "is_loan": True,
                "company_id": cls.company.id,
                "installment_ids": [(0, 0, {"name": "3", "divisor": 3, "surcharge_coefficient": 1.2})],
            }
        )
        cls.invoice = cls.init_invoice("out_invoice", amounts=[1000.0], post=True)
        cls.billing_user = new_test_user(
            cls.env,
            login="loan_billing_user",
            groups="account.group_account_invoice",
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )

    def _new_wizard(self, vals=None):
        receivable = self.invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        return (
            self.env["account.loan.register"]
            .with_user(self.billing_user)
            .with_context(active_ids=receivable.ids)
            .create({"card_id": self.card.id, **(vals or {})})
        )

    def test_terms_default_to_company_terms(self):
        wizard = self._new_wizard()
        self.assertEqual(wizard.loan_terms, "<p>Company terms</p>")

    def test_billing_user_edits_terms_only_for_the_loan(self):
        wizard = self._new_wizard({"loan_terms": "<p>Only this loan</p>"})

        self.assertEqual(self.company.loan_terms, "<p>Company terms</p>")
        self.assertIn("Only this loan", wizard._prepare_loan_move_data()["loan_description"])
