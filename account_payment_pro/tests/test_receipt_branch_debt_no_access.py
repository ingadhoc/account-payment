# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestReceiptBranchDebtNoAccess(AccountTestInvoicingCommon):
    """Un usuario que trabaja solo en una sucursal cobra la factura de otra a la que no
    tiene acceso, cuando la raíz no bloquea la conciliación entre compañías."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_company = cls.company_data["company"]
        cls.root_company.write(
            {
                "block_intercompany_conciliation": "none",
                "child_ids": [
                    Command.create({"name": "Branch A"}),
                    Command.create({"name": "Branch B"}),
                ],
            }
        )
        cls.cr.precommit.run()  # load the CoA
        cls.branch_a, cls.branch_b = cls.root_company.child_ids
        (cls.root_company + cls.branch_a + cls.branch_b).use_payment_pro = True

        cls.invoice_b = cls.init_invoice("out_invoice", amounts=[100.0], company=cls.branch_b, post=True)
        cls.bank_a = cls.env["account.journal"].create(
            {"name": "Bank A", "code": "ZBA", "type": "bank", "company_id": cls.branch_a.id}
        )
        # Without an account on the method line the payment has no entry to reconcile.
        cls.bank_a.inbound_payment_method_line_ids.payment_account_id = cls.bank_a.default_account_id
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "Branch A accountant",
                "login": "branch_a_receipts",
                "company_id": cls.branch_a.id,
                "company_ids": [Command.set(cls.branch_a.ids)],
                "group_ids": [
                    Command.set(
                        (
                            cls.env.ref("account.group_account_manager")
                            + cls.env.ref("account_ux.group_read_branch_debt")
                        ).ids
                    )
                ],
            }
        )

    def _new_receipt(self):
        payment = (
            self.env["account.payment"]
            .with_user(self.user_a)
            .with_context(allowed_company_ids=self.branch_a.ids)
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "company_id": self.branch_a.id,
                    "journal_id": self.bank_a.id,
                    "amount": self.invoice_b.amount_total,
                }
            )
        )
        payment.action_add_all()
        return payment

    def test_the_receipt_collects_the_debt_of_a_branch_without_access(self):
        payment = self._new_receipt()
        self.assertEqual(payment.to_pay_move_line_ids.move_id, self.invoice_b)

        payment.action_post()

        self.assertEqual(payment.company_id, self.branch_a)
        self.assertEqual(self.invoice_b.payment_state, "paid")

    def test_the_receipt_goes_back_to_draft_and_releases_the_debt(self):
        payment = self._new_receipt()
        payment.action_post()

        payment.action_draft()

        self.assertEqual(payment.state, "draft")
        self.assertEqual(self.invoice_b.payment_state, "not_paid")

        payment.action_post()

        self.assertEqual(self.invoice_b.payment_state, "paid")

    def test_without_the_group_the_receipt_does_not_offer_other_branches(self):
        self.user_a.group_ids -= self.env.ref("account_ux.group_read_branch_debt")
        self.assertFalse(self._new_receipt().to_pay_move_line_ids)

    def test_the_receipt_is_not_posted_with_debt_it_can_no_longer_collect(self):
        payment = self._new_receipt()
        self.root_company.block_intercompany_conciliation = "all"

        with self.assertRaises(ValidationError):
            payment.action_post()
