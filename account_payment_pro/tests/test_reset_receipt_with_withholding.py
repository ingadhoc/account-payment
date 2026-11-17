# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestResetReceiptWithWithholding(AccountTestInvoicingCommon):
    """A posted receipt with a withholding goes back to draft without the entry falling out of balance."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.use_payment_pro = True
        cls.company.withholding_tax_base_account_id = cls.env["account.account"].create(
            {"code": "WITHB", "name": "Withholding Tax Base", "account_type": "asset_current"}
        )
        cls.withholding_tax = cls.env["account.tax"].create(
            {
                "name": "Withholding 2%",
                "amount_type": "percent",
                "amount": -2.0,
                "type_tax_use": "sale",
                "is_withholding_tax": True,
            }
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _posted_receipt(self, amount=1000.0, withholding_base=1000.0, journal=None):
        invoice = self.init_invoice("out_invoice", partner=self.partner_a, amounts=[amount], taxes=[], post=True)
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": (journal or self.bank_journal).id,
                "amount": amount,
                "to_pay_move_line_ids": [
                    Command.set(
                        invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable").ids
                    )
                ],
            }
        )
        payment.withholding_line_ids = [
            Command.create({"tax_id": self.withholding_tax.id, "base_amount": withholding_base})
        ]
        payment.action_post()
        return payment

    def test_a_posted_receipt_with_a_withholding_goes_back_to_draft(self):
        payment = self._posted_receipt()
        self.assertEqual(payment.move_id.state, "posted")

        payment.action_draft()

        self.assertEqual(payment.state, "draft")
        self.assertEqual(
            sum(payment.move_id.line_ids.mapped("balance")), 0.0, "the entry of the draft payment is balanced"
        )

    def test_the_draft_receipt_can_be_posted_again(self):
        payment = self._posted_receipt()
        payment.action_draft()

        payment.action_post()

        self.assertEqual(payment.move_id.state, "posted")
        self.assertEqual(sum(payment.move_id.line_ids.mapped("balance")), 0.0)

    def test_a_receipt_paid_in_cash_also_goes_back_to_draft(self):
        cash_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "cash")], limit=1
        )
        payment = self._posted_receipt(journal=cash_journal)

        payment.action_draft()

        self.assertEqual(payment.state, "draft")
        self.assertEqual(sum(payment.move_id.line_ids.mapped("balance")), 0.0)
