##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command, fields
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestAmountFromChecks(TestArCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_ri
        cls.company.use_payment_pro = True
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.partner = cls.res_partner_adhoc
        cls.receivable = cls.partner.with_company(cls.company).property_account_receivable_id
        cls.income = cls.env["account.account"].search(
            [("company_ids", "in", cls.company.id), ("account_type", "=", "income")], limit=1
        )
        cls.misc_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "general")], limit=1
        )
        cls.debt_line = cls._create_debt(1_200_000)
        cls._create_debt(300_000)

    @classmethod
    def _create_debt(cls, amount):
        move = cls.env["account.move"].create(
            {
                "journal_id": cls.misc_journal.id,
                "date": fields.Date.today(),
                "line_ids": [
                    Command.create({"account_id": cls.receivable.id, "partner_id": cls.partner.id, "debit": amount}),
                    Command.create({"account_id": cls.income.id, "credit": amount}),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == cls.receivable)

    def _receipt_form(self, method_code):
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

    def test_amount_from_checks_after_changing_debt(self):
        receipt = self._receipt_form("new_third_party_checks")
        with receipt.l10n_latam_new_check_ids.new() as check:
            check.name = "00000001"
            check.payment_date = fields.Date.today()
            check.amount = 1_000_000
        receipt.to_pay_move_line_ids.clear()
        receipt.to_pay_move_line_ids.add(self.debt_line)
        # the debt onchange still moves the amount away from the checks
        self.assertEqual(receipt.amount, 1_200_000)
        payment = receipt.save()
        payment.action_amount_from_checks()
        self.assertEqual(payment.amount, 1_000_000)
        self.assertEqual(payment.payment_difference, 200_000)
        payment.action_post()
        # in_process or paid depending on the journal outstanding account
        self.assertIn(payment.state, ("in_process", "paid"))

    def test_amount_from_checks_ignores_other_methods(self):
        receipt = self._receipt_form("manual")
        receipt.amount = 1_000_000
        payment = receipt.save()
        payment.action_amount_from_checks()
        self.assertEqual(payment.amount, 1_000_000)
