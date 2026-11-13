# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestAmountFollowsDebt(AccountTestInvoicingCommon):
    """When the selected debt changes, the amount of a supplier payment follows it as in 19.0: when the
    withholdings change or the partner changes, never on its own."""

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
                "type_tax_use": "purchase",
                "is_withholding_tax": True,
            }
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _bill(self, partner, amount):
        return self.init_invoice("in_invoice", partner=partner, amounts=[amount], taxes=[], post=True)

    def _new_payment_form(self):
        form = Form(
            self.env["account.payment"].with_context(default_partner_type="supplier", default_payment_type="outbound")
        )
        form.journal_id = self.bank_journal
        return form

    def test_changing_the_partner_moves_the_amount_to_its_debt(self):
        self._bill(self.partner_a, 400.0)
        bill_b = self._bill(self.partner_b, 100.0)
        form = self._new_payment_form()
        form.partner_id = self.partner_a
        self.assertEqual(form.amount, 400.0)

        form.partner_id = self.partner_b

        self.assertEqual(form.amount, bill_b.amount_total, "the amount goes down to the debt of the new partner")

    def test_changing_the_withholdings_moves_the_amount_to_the_debt(self):
        bill_1 = self._bill(self.partner_a, 100.0)
        self._bill(self.partner_a, 300.0)
        form = self._new_payment_form()
        form.partner_id = self.partner_a
        self.assertEqual(form.amount, 400.0)
        payment = form.save()
        payment.withholding_line_ids = [Command.create({"tax_id": self.withholding_tax.id, "base_amount": 400.0})]
        other_line = payment.to_pay_move_line_ids.filtered(lambda line: line.move_id != bill_1)

        with Form(payment) as form:
            form.to_pay_move_line_ids.remove(id=other_line.id)
            with form.withholding_line_ids.edit(0) as line:
                line.base_amount = 100.0

        self.assertEqual(payment.amount, 100.0, "the gross amount is the selected debt")
        self.assertEqual(payment.withholding_net_amount, 98.0)

    def test_without_a_change_of_withholdings_the_amount_is_kept(self):
        bill_1 = self._bill(self.partner_a, 100.0)
        self._bill(self.partner_a, 300.0)
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "journal_id": self.bank_journal.id,
                "amount": 400.0,
            }
        )
        other_line = payment.to_pay_move_line_ids.filtered(lambda line: line.move_id != bill_1)

        with Form(payment) as form:
            form.to_pay_move_line_ids.remove(id=other_line.id)

        self.assertEqual(payment.selected_debt, 100.0)
        self.assertEqual(payment.amount, 400.0, "as in 19.0, removing a bill alone does not touch the amount")
