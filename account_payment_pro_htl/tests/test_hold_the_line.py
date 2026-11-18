from datetime import timedelta

from odoo import Command, fields
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestHoldTheLine(TestArCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_ri
        cls.company.use_payment_pro = True
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.today = fields.Date.today()
        cls.partner = cls.res_partner_adhoc
        cls.receivable = cls.partner.with_company(cls.company).property_account_receivable_id
        cls.income = cls.env["account.account"].search(
            [("company_ids", "in", cls.company.id), ("account_type", "=", "income")], limit=1
        )
        cls.misc_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "general")], limit=1
        )
        cls.big_debt = cls._create_debt(1_200_000)
        cls.small_debt = cls._create_debt(300_000)

    @classmethod
    def _create_debt(cls, amount):
        move = cls.env["account.move"].create(
            {
                "journal_id": cls.misc_journal.id,
                "date": cls.today,
                "line_ids": [
                    Command.create({"account_id": cls.receivable.id, "partner_id": cls.partner.id, "debit": amount}),
                    Command.create({"account_id": cls.income.id, "credit": amount}),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == cls.receivable)

    def _receipt_form(self, method_code="manual"):
        method_line = self.env["account.payment.method.line"].search(
            [
                ("journal_id.company_id", "=", self.company.id),
                ("payment_type", "=", "inbound"),
                ("code", "=", method_code),
            ],
            limit=1,
        )
        receipt = Form(
            self.env["account.payment"].with_context(default_payment_type="inbound", default_partner_type="customer")
        )
        receipt.partner_id = self.partner
        receipt.journal_id = method_line.journal_id
        receipt.payment_method_line_id = method_line
        return receipt

    def test_debt_follows_amount_when_empty(self):
        receipt = self._receipt_form()
        self.assertEqual(receipt.amount, 1_500_000)

    def test_removing_debt_keeps_amount(self):
        receipt = self._receipt_form()
        receipt.amount = 1_000_000
        receipt.to_pay_move_line_ids.remove(id=self.small_debt.id)
        self.assertEqual(receipt.amount, 1_000_000)
        self.assertEqual(receipt.payment_difference, 200_000)

    def test_unlocked_amount_follows_debt(self):
        receipt = self._receipt_form()
        self.assertTrue(receipt.amount_locked)
        receipt.amount = 1_000_000
        receipt.amount_locked = False
        receipt.to_pay_move_line_ids.remove(id=self.small_debt.id)
        # standard behavior: the amount is raised up to the remaining debt
        self.assertEqual(receipt.amount, 1_200_000)
        self.assertEqual(receipt.payment_difference, 0)

    def test_adding_debt_keeps_amount(self):
        receipt = self._receipt_form()
        receipt.to_pay_move_line_ids.clear()
        receipt.amount = 1_000_000
        receipt.to_pay_move_line_ids.add(self.big_debt)
        self.assertEqual(receipt.amount, 1_000_000)

    def test_changing_debt_keeps_checks_amount(self):
        receipt = self._receipt_form("new_third_party_checks")
        with receipt.l10n_latam_new_check_ids.new() as check:
            check.name = "00000001"
            check.payment_date = self.today
            check.amount = 1_000_000
        receipt.to_pay_move_line_ids.clear()
        receipt.to_pay_move_line_ids.add(self.big_debt)
        self.assertEqual(receipt.amount, 1_000_000)
        payment = receipt.save()
        payment.action_post()
        self.assertIn(payment.state, ("in_process", "paid"))

    def test_proposed_amount_still_follows_debt(self):
        usd = self.env["res.currency"].with_context(active_test=False).search([("name", "=", "USD")])
        usd.active = True
        old_date = self.today - timedelta(days=10)
        self.env["res.currency.rate"].create(
            [
                {"name": old_date, "currency_id": usd.id, "company_id": self.company.id, "inverse_company_rate": 1000},
                {
                    "name": self.today,
                    "currency_id": usd.id,
                    "company_id": self.company.id,
                    "inverse_company_rate": 1200,
                },
            ]
        )
        sale_journal = self.env["account.journal"].create(
            {
                "name": "Ventas HTL",
                "type": "sale",
                "code": "HTLS",
                "company_id": self.company.id,
                "l10n_latam_use_documents": False,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner.id,
                "move_type": "out_invoice",
                "invoice_date": old_date,
                "date": old_date,
                "journal_id": sale_journal.id,
                "currency_id": usd.id,
                "invoice_line_ids": [
                    Command.create({"name": "Test", "quantity": 1, "price_unit": 100, "tax_ids": [Command.clear()]})
                ],
            }
        )
        invoice.action_post()
        context = invoice.action_register_payment()["context"]
        receipt = Form(self.env["account.payment"].with_context(**context))
        # the amount proposed by register payment is at the invoice rate (100 USD x 1000)
        self.assertEqual(receipt.amount, 100_000)
        debt = receipt.to_pay_move_line_ids[0]
        receipt.to_pay_move_line_ids.clear()
        receipt.to_pay_move_line_ids.add(debt)
        # still proposed, so it follows the debt at today's rate
        self.assertAlmostEqual(receipt.amount, 120_000, delta=10)
        self.assertAlmostEqual(receipt.payment_difference, 0, delta=0.01)
