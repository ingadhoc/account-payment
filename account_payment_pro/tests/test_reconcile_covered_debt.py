# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestReconcileCoveredDebt(AccountTestInvoicingCommon):
    """A payment that covers only part of the selected debt must fully reconcile what it pays.

    The debt lines the payment does not reach used to go into the same reconcile() call, so the
    core never created the full reconcile and the paid invoice kept a partial matching number.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.use_payment_pro = True

    def test_payment_fully_reconciles_the_invoice_it_covers(self):
        invoice_a = self._create_invoice_one_line(price_unit=5000.0, invoice_date="2019-01-01", post=True)
        invoice_b = self._create_invoice_one_line(price_unit=7500.0, invoice_date="2019-01-02", post=True)
        line_a = invoice_a.line_ids.filtered(lambda line: line.account_type == "asset_receivable")
        line_b = invoice_b.line_ids.filtered(lambda line: line.account_type == "asset_receivable")

        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "inbound",
                "partner_type": "customer",
                "amount": invoice_a.amount_total,
                "journal_id": self.company_data["default_journal_bank"].id,
                "to_pay_move_line_ids": [Command.set((line_a + line_b).ids)],
            }
        )
        payment.action_post()

        self.assertTrue(line_a.full_reconcile_id)
        self.assertFalse(line_a.matching_number.startswith("P"))
        self.assertIn(invoice_a.payment_state, ("paid", "in_payment"))
        self.assertFalse(line_b.matched_credit_ids)
        self.assertEqual(invoice_b.amount_residual, invoice_b.amount_total)
