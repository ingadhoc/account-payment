# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestReceiptAmountKeepsNet(AccountTestInvoicingCommon):
    """In a customer receipt the withholdings do not move the amount the user typed, as in 19.0: the gross
    grows and the gap shows up as the difference to adjust."""

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

    def _receipt_form(self, partner):
        form = Form(
            self.env["account.payment"].with_context(default_partner_type="customer", default_payment_type="inbound")
        )
        form.journal_id = self.bank_journal
        form.partner_id = partner
        return form

    def _add_withholding(self, form, base_amount):
        with form.withholding_line_ids.new() as line:
            line.tax_id = self.withholding_tax
            line.base_amount = base_amount

    def test_the_withholding_does_not_move_the_amount_of_a_receipt(self):
        self.init_invoice("out_invoice", partner=self.partner_a, amounts=[1000.0], taxes=[], post=True)
        form = self._receipt_form(self.partner_a)
        self.assertEqual(form.amount, 1000.0)

        self._add_withholding(form, 1000.0)

        self.assertEqual(form.withholding_net_amount, 1000.0, "the net the user sees stays where it was")
        self.assertEqual(form.amount, 1020.0, "the gross grows by the withholding")
        self.assertEqual(form.payment_total, 1020.0)
        self.assertEqual(form.payment_difference, -20.0, "the difference is left for the user to adjust")

    def test_editing_the_withholding_moves_the_gross_by_the_delta(self):
        self.init_invoice("out_invoice", partner=self.partner_a, amounts=[1000.0], taxes=[], post=True)
        form = self._receipt_form(self.partner_a)
        self._add_withholding(form, 1000.0)

        with form.withholding_line_ids.edit(0) as line:
            line.base_amount = 500.0

        self.assertEqual(form.withholding_net_amount, 1000.0, "the net is still the one the user typed")
        self.assertEqual(form.amount, 1010.0, "only the delta of the withholding moved the gross")

    def test_the_supplier_payment_still_follows_the_debt(self):
        purchase_withholding = self.env["account.tax"].create(
            {
                "name": "Withholding 2% purchase",
                "amount_type": "percent",
                "amount": -2.0,
                "type_tax_use": "purchase",
                "is_withholding_tax": True,
            }
        )
        self.init_invoice("in_invoice", partner=self.partner_a, amounts=[1000.0], taxes=[], post=True)
        form = Form(
            self.env["account.payment"].with_context(default_partner_type="supplier", default_payment_type="outbound")
        )
        form.journal_id = self.bank_journal
        form.partner_id = self.partner_a
        with form.withholding_line_ids.new() as line:
            line.tax_id = purchase_withholding
            line.base_amount = 1000.0

        self.assertEqual(form.amount, 1000.0, "the gross stays on the debt")
        self.assertEqual(form.withholding_net_amount, 980.0, "the net is what goes through the bank")
        self.assertEqual(form.payment_difference, 0.0)
