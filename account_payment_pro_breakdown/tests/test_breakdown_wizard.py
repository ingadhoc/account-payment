##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import BreakdownCommon


@tagged("post_install", "-at_install")
class TestBreakdownWizard(BreakdownCommon):
    def setUp(self):
        super().setUp()
        self.debts = self._debt(80000) + self._debt(80000)
        self.payment = self._payment(100000, self.debts)

    def test_wizard_lists_the_selected_debts_by_due_date(self):
        earlier = self._debt(50000, date=fields.Date.subtract(self.today, days=10))
        payment = self._payment(100000, self.debts + earlier)
        action = payment.action_open_breakdown_wizard()
        wizard = Form(self.env[action["res_model"]].with_context(**action["context"])).save()
        self.assertEqual(wizard.total_amount, 100000)
        self.assertEqual(wizard.line_ids.move_line_id.ids, (earlier + self.debts).ids)
        self.assertEqual(wizard.line_ids.mapped("amount_residual"), [50000, 80000, 80000])
        self.assertEqual(wizard.line_ids.mapped("amount"), [0, 0, 0])

    def test_remove_all_drops_the_breakdown(self):
        self._break_down(self.payment, [60000, 40000])
        self.payment.remove_all()
        self.assertFalse(self.payment.breakdown_ids)

    def test_amounts_must_add_up_to_the_payment(self):
        with self.assertRaisesRegex(UserError, "add up to the payment amount"):
            self._break_down(self.payment, [60000, 30000])
        self.assertFalse(self.payment.breakdown_ids)

    def test_a_debt_cant_receive_more_than_it_owes(self):
        with self.assertRaisesRegex(UserError, "more than they owe"):
            self._break_down(self.payment, [90000, 10000])

    def test_breakdown_is_saved_and_loaded_again(self):
        self._break_down(self.payment, [60000, 40000])
        self.assertEqual(self.payment.breakdown_ids.mapped("amount"), [60000, 40000])
        self.assertEqual(self.payment.breakdown_ids.move_line_id, self.debts)
        action = self.payment.action_open_breakdown_wizard()
        wizard = self.env[action["res_model"]].with_context(**action["context"]).create({})
        self.assertEqual(wizard.line_ids.mapped("amount"), [60000, 40000])
        self.assertEqual(wizard.difference, 0)

    def test_a_debt_without_amount_is_left_out(self):
        self.payment.amount = 80000
        self._break_down(self.payment, [80000, 0])
        self.assertEqual(self.payment.breakdown_ids.move_line_id, self.debts[0])

    def test_not_offered_with_write_off(self):
        self.payment.write_off_amount = 10
        with self.assertRaisesRegex(UserError, "write-off or withholdings"):
            self.payment.action_open_breakdown_wizard()

    def test_tab_edits_show_the_difference(self):
        self._break_down(self.payment, [60000, 40000])
        payment_form = Form(self.payment)
        with payment_form.breakdown_ids.edit(1) as line:
            line.amount = 30000
        payment_form.save()
        self.assertTrue(self.payment.breakdown_mismatch)
        self.assertEqual(self.payment.breakdown_difference, 10000)
        payment_form = Form(self.payment)
        payment_form.breakdown_ids.remove(1)
        payment_form.breakdown_ids.remove(0)
        payment_form.save()
        self.assertFalse(self.payment.breakdown_ids)
        self.assertFalse(self.payment.breakdown_mismatch)
