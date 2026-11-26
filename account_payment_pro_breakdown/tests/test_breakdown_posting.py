##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BreakdownCommon


@tagged("post_install", "-at_install")
class TestBreakdownPosting(BreakdownCommon):
    def test_each_part_goes_to_its_debt(self):
        debts = self._debt(80000) + self._debt(80000)
        payment = self._payment(100000, debts)
        self._break_down(payment, [60000, 40000])
        payment.action_post()
        counterparts = self._counterparts(payment)
        self.assertEqual(counterparts.mapped("balance"), [-60000, -40000])
        self.assertEqual(counterparts.breakdown_debt_line_id, debts)
        self.assertTrue(all(counterparts.mapped("reconciled")))
        self.assertResiduals(debts, [20000, 40000])

    def test_payment_without_breakdown_is_unchanged(self):
        debts = self._debt(80000) + self._debt(80000)
        payment = self._payment(100000, debts)
        payment.action_post()
        self.assertEqual(len(self._counterparts(payment)), 1)
        self.assertEqual(sorted(abs(debt.amount_residual) for debt in debts), [0, 60000])

    def test_supplier_payment_with_three_bills(self):
        debts = self._debt(50000, "in_invoice") + self._debt(50000, "in_invoice") + self._debt(50000, "in_invoice")
        payment = self._payment(60000, debts, payment_type="outbound")
        self._break_down(payment, [10000, 20000, 30000])
        payment.action_post()
        self.assertEqual(self._counterparts(payment).mapped("balance"), [10000, 20000, 30000])
        self.assertResiduals(debts, [40000, 30000, 20000])

    def test_supplier_payment_with_credit_card(self):
        card_journal = self.env["account.journal"].create({"name": "Card BD", "type": "credit", "code": "CRDBD"})
        card_journal.outbound_payment_method_line_ids.payment_account_id = card_journal.default_account_id
        debts = self._debt(50000, "in_invoice") + self._debt(50000, "in_invoice")
        payment = self._payment(70000, debts, payment_type="outbound", journal_id=card_journal.id)
        self.assertEqual(payment.outstanding_account_id.account_type, "liability_credit_card")
        self._break_down(payment, [20000, 50000])
        payment.action_post()
        self.assertEqual(payment.move_id.state, "posted")
        self.assertTrue(all(self._counterparts(payment).mapped("reconciled")))
        self.assertResiduals(debts, [30000, 0])

    def test_two_own_checks_against_three_bills(self):
        checks_account = self.env["account.account"].create(
            {
                "name": "Deferred Checks BD",
                "code": "BDDEFCHK",
                "account_type": "asset_current",
                "reconcile": True,
                "company_ids": [Command.set(self.company.ids)],
            }
        )
        own_checks = self.env["account.payment.method.line"].create(
            {
                "payment_method_id": self.env.ref("l10n_latam_check.account_payment_method_own_checks").id,
                "name": "Own Checks",
                "payment_account_id": checks_account.id,
                "journal_id": self.bank_journal.id,
            }
        )
        debts = self._debt(50000, "in_invoice") + self._debt(50000, "in_invoice") + self._debt(50000, "in_invoice")
        payment = self._payment(
            100000,
            debts,
            payment_type="outbound",
            payment_method_line_id=own_checks.id,
            l10n_latam_new_check_ids=[
                Command.create({"name": "00000101", "amount": 70000, "payment_date": self.today}),
                Command.create({"name": "00000102", "amount": 30000, "payment_date": self.today}),
            ],
        )
        self._break_down(payment, [50000, 30000, 20000])
        payment.action_post()
        liquidity = payment.move_id.line_ids.filtered("l10n_latam_check_ids")
        self.assertEqual(sorted(liquidity.mapped("balance")), [-70000, -30000])
        self.assertResiduals(debts, [0, 20000, 30000])

    def test_foreign_currency_debts_with_exchange_difference(self):
        yesterday = fields.Date.subtract(self.today, days=1)
        self.env["res.currency.rate"].create(
            [
                {
                    "name": yesterday,
                    "currency_id": self.foreign_currency.id,
                    "company_id": self.company.id,
                    "inverse_company_rate": 1100,
                },
                {
                    "name": self.today,
                    "currency_id": self.foreign_currency.id,
                    "company_id": self.company.id,
                    "inverse_company_rate": 1200,
                },
            ]
        )
        debts = self._debt(1000, currency=self.foreign_currency, date=yesterday) + self._debt(
            1000, currency=self.foreign_currency, date=yesterday
        )
        payment = self._payment(1, debts)
        self.assertEqual(payment.counterpart_currency_id, self.foreign_currency)
        payment.counterpart_rate = 1 / 1200
        payment.counterpart_currency_amount = 1000
        self._break_down(payment, [600, 400])
        payment.action_post()
        counterparts = self._counterparts(payment)
        self.assertEqual(counterparts.mapped("amount_currency"), [-600, -400])
        self.assertEqual(counterparts.mapped("balance"), [-720000, -480000])
        self.assertResiduals(debts, [400, 600], field="amount_residual_currency")
        self.assertResiduals(debts, [440000, 660000])

    def test_foreign_currency_rounding_goes_to_the_last_part(self):
        self.env["res.currency.rate"].create(
            {
                "name": self.today,
                "currency_id": self.foreign_currency.id,
                "company_id": self.company.id,
                "inverse_company_rate": 1000,
            }
        )
        debts = (
            self._debt(1000, currency=self.foreign_currency)
            + self._debt(1000, currency=self.foreign_currency)
            + self._debt(1000, currency=self.foreign_currency)
        )
        payment = self._payment(1, debts)
        # 1000 at 1000.001 is 1000001: a third of it does not round to the cent.
        payment.counterpart_rate = 1 / 1000.001
        payment.counterpart_currency_amount = 1000
        self._break_down(payment, [333.33, 333.33, 333.34])
        payment.action_post()
        counterparts = self._counterparts(payment)
        self.assertEqual(counterparts.mapped("amount_currency"), [-333.33, -333.33, -333.34])
        self.assertEqual(counterparts.mapped("balance"), [-333330.33, -333330.33, -333340.34])
        self.assertResiduals(debts, [666.67, 666.67, 666.66], field="amount_residual_currency")


@tagged("post_install", "-at_install")
class TestBreakdownBlocks(BreakdownCommon):
    def setUp(self):
        super().setUp()
        self.debts = self._debt(80000) + self._debt(80000)
        self.payment = self._payment(100000, self.debts)
        self._break_down(self.payment, [60000, 40000])

    def test_breakdown_that_does_not_add_up(self):
        self.payment.breakdown_ids[1].amount = 30000
        with self.assertRaisesRegex(UserError, "does not add up"):
            self.payment.action_post()

    def test_debt_no_longer_selected(self):
        self.payment.to_pay_move_line_ids = [Command.unlink(self.debts[1].id)]
        with self.assertRaisesRegex(UserError, "no longer selected"):
            self.payment.action_post()

    def test_debt_paid_by_another_payment_in_between(self):
        self._payment(50000, self.debts[0]).action_post()
        with self.assertRaisesRegex(UserError, "more than they owe"):
            self.payment.action_post()

    def test_write_off_added_after_the_breakdown(self):
        self.payment.write_off_amount = 10
        with self.assertRaisesRegex(UserError, "can't be combined yet"):
            self.payment.action_post()

    def test_back_to_draft_and_edit(self):
        self.payment.action_post()
        self.payment.action_draft()
        # A change the core synchronizes to the entry keeps the parts.
        self.payment.date = fields.Date.add(self.today, days=1)
        self.assertEqual(self._counterparts(self.payment).mapped("balance"), [-60000, -40000])
        # A new amount leaves the breakdown out of date: a single counterpart and the posting blocked.
        self.payment.amount = 110000
        self.assertEqual(self._counterparts(self.payment).mapped("balance"), [-110000])
        with self.assertRaisesRegex(UserError, "does not add up"):
            self.payment.action_post()
        self._break_down(self.payment, [70000, 40000])
        self.payment.action_post()
        self.assertResiduals(self.debts, [10000, 40000])
