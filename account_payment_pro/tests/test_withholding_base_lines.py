# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestWithholdingBaseLines(AccountTestInvoicingCommon):
    """Two withholdings over the same base leave one pair of base journal items, as in 19.0."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.use_payment_pro = True
        cls.base_account = cls.env["account.account"].create(
            {"code": "WITHB", "name": "Withholding Tax Base", "account_type": "asset_current"}
        )
        cls.company.withholding_tax_base_account_id = cls.base_account
        cls.tax_a, cls.tax_b = cls.env["account.tax"].create(
            [
                {
                    "name": "Withholding 3%",
                    "amount_type": "percent",
                    "amount": -3.0,
                    "type_tax_use": "purchase",
                    "is_withholding_tax": True,
                },
                {
                    "name": "Withholding 2%",
                    "amount_type": "percent",
                    "amount": -2.0,
                    "type_tax_use": "purchase",
                    "is_withholding_tax": True,
                },
            ]
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _payment(self, withholdings):
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "journal_id": self.bank_journal.id,
                "amount": 1000.0,
            }
        )
        payment.withholding_line_ids = [
            Command.create({"tax_id": tax.id, "base_amount": base}) for tax, base in withholdings
        ]
        payment.action_post()
        return payment

    def _base_lines(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.base_account and not line.tax_repartition_line_id
        )

    def test_two_withholdings_over_the_same_base_leave_one_pair(self):
        payment = self._payment([(self.tax_a, 1000.0), (self.tax_b, 1000.0)])

        base_lines = self._base_lines(payment)

        self.assertEqual(len(base_lines), 2, "one base journal item and its counterpart, not one pair per tax")
        self.assertEqual(sorted(base_lines.mapped("balance")), [-1000.0, 1000.0])
        self.assertEqual(len(payment.move_id.line_ids), 6, "bank, payable, two withholdings and the base pair")

    def test_withholdings_over_different_bases_keep_their_own_pair(self):
        payment = self._payment([(self.tax_a, 1000.0), (self.tax_b, 400.0)])

        base_lines = self._base_lines(payment)

        self.assertEqual(len(base_lines), 4, "a different base is a different pair, as in 19.0")
        self.assertEqual(sorted(base_lines.mapped("balance")), [-1000.0, -400.0, 400.0, 1000.0])

    def test_a_single_withholding_still_leaves_its_pair(self):
        payment = self._payment([(self.tax_a, 1000.0)])

        self.assertEqual(len(self._base_lines(payment)), 2)
