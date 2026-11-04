# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestWithholdingGrossAmount(AccountTestInvoicingCommon):
    """In 20 the payment amount is the gross one (paid + withheld). With payment pro the user
    keeps working with the net amount and the withholding mode follows the withholding lines."""

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

    def _payment(self, withholding_base=1000.0, **vals):
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "journal_id": self.bank_journal.id,
                "amount": 1000.0,
                **vals,
            }
        )
        if withholding_base:
            payment.withholding_line_ids = [
                Command.create({"tax_id": self.withholding_tax.id, "base_amount": withholding_base})
            ]
        return payment

    def test_the_user_types_the_net_amount_and_the_payment_keeps_the_gross_one(self):
        payment = self._payment()
        self.assertEqual(payment.withholding_amount, 20.0)

        payment.withholding_net_amount = 980.0

        self.assertEqual(payment.amount, 1000.0, "gross = net + withholdings")
        self.assertEqual(payment.amount_exact, 1000.0)
        self.assertEqual(payment.payment_total, 1000.0, "the payment total already includes the withholdings")

    def test_list_amounts_show_the_net_amount(self):
        payment = self._payment()
        self.assertEqual(payment.withholding_net_amount_signed, -980.0)
        self.assertEqual(payment.amount_company_currency_signed, -980.0, "a draft shows what goes through the bank")
        payment.action_post()
        self.assertEqual(payment.amount_company_currency_signed, -980.0)

    def test_the_debt_currency_amount_is_also_net(self):
        foreign = self.setup_other_currency("EUR", rates=[("2000-01-01", 1.0)])
        payment = self._payment()
        payment.counterpart_currency_id = foreign
        payment.counterpart_rate = 0.5
        payment.counterpart_currency_amount = 500.0
        self.assertEqual(payment.counterpart_currency_net_amount, 490.0, "500 gross - 20 withheld * 0.5")

        payment.counterpart_currency_net_amount = 480.0

        self.assertEqual(payment.counterpart_currency_amount, 490.0)
        self.assertEqual(payment.amount, 980.0)

    def test_the_mode_follows_the_withholding_lines(self):
        payment = self._payment(withholding_base=0.0)
        self.assertEqual(payment.withhold, "payment")

        payment.withholding_line_ids = [Command.create({"tax_id": self.withholding_tax.id, "base_amount": 1000.0})]
        self.assertEqual(payment.withhold, "withhold_pay")

        payment.withholding_net_amount = 0.0
        self.assertEqual(payment.amount, 20.0)
        self.assertEqual(payment.withhold, "withhold", "nothing goes through the bank")

    def test_the_entry_pays_the_net_and_cancels_the_gross(self):
        payment = self._payment()
        payment.action_post()

        liquidity, counterpart, _writeoff = payment._seek_for_lines()
        tax_line = payment.move_id.line_ids.filtered(lambda line: line.tax_line_id == self.withholding_tax)
        self.assertEqual(sum(liquidity.mapped("balance")), -980.0)
        self.assertEqual(sum(counterpart.mapped("balance")), 1000.0)
        self.assertEqual(tax_line.balance, -20.0)

    def test_a_withholding_only_payment_has_no_bank_line(self):
        payment = self._payment(amount=20.0)
        self.assertEqual(payment.withhold, "withhold")
        payment.action_post()

        liquidity, counterpart, _writeoff = payment._seek_for_lines()
        self.assertFalse(liquidity)
        self.assertEqual(sum(counterpart.mapped("balance")), 20.0)

    def test_a_foreign_currency_withholding_uses_the_rate_of_the_payment(self):
        foreign = self.setup_other_currency("EUR", rates=[("2000-01-01", 1.0)])
        payment = self._payment(currency_id=foreign.id)
        # 1 company unit = 0.5 EUR → 1 EUR = 2 company units, not the 1:1 of the day
        payment.accounting_rate = 0.5
        payment.action_post()

        liquidity, counterpart, _writeoff = payment._seek_for_lines()
        tax_line = payment.move_id.line_ids.filtered(lambda line: line.tax_line_id == self.withholding_tax)
        self.assertEqual(tax_line.amount_currency, -20.0)
        self.assertEqual(tax_line.balance, -40.0)
        self.assertEqual(sum(liquidity.mapped("balance")), -1960.0)
        self.assertEqual(sum(counterpart.mapped("balance")), 2000.0)


@tagged("post_install", "-at_install")
class TestWithholdingGrossAmountChecks(TestArCommon):
    """With checks the checks are the net amount: the gross one adds the withholdings."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_ri
        cls.company.use_payment_pro = True
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        if not cls.company.withholding_tax_base_account_id:
            cls.company.withholding_tax_base_account_id = cls.env["account.account"].create(
                {"code": "WITHB", "name": "Withholding Tax Base", "account_type": "asset_current"}
            )
        cls.withholding_tax = cls.env["account.tax"].create(
            {
                "name": "Suffered withholding 2%",
                "amount_type": "percent",
                "amount": -2.0,
                "type_tax_use": "sale",
                "is_withholding_tax": True,
                "company_id": cls.company.id,
            }
        )
        cls.method_line = cls.env["account.payment.method.line"].search(
            [
                ("journal_id.company_id", "=", cls.company.id),
                ("payment_type", "=", "inbound"),
                ("code", "=", "new_third_party_checks"),
            ],
            limit=1,
        )

    def test_the_checks_are_the_net_amount(self):
        receipt = Form(
            self.env["account.payment"].with_context(default_payment_type="inbound", default_partner_type="customer")
        )
        receipt.partner_id = self.res_partner_adhoc
        receipt.journal_id = self.method_line.journal_id
        receipt.payment_method_line_id = self.method_line
        with receipt.l10n_latam_new_check_ids.new() as check:
            check.name = "00000001"
            check.payment_date = fields.Date.today()
            check.amount = 980.0
        payment = receipt.save()
        payment.withholding_line_ids = [Command.create({"tax_id": self.withholding_tax.id, "base_amount": 1000.0})]

        self.assertEqual(payment.amount, 1000.0, "gross = checks + withholdings")
        self.assertEqual(payment.withholding_net_amount, 980.0)
        self.assertEqual(payment.withhold, "withhold_pay")
        self.assertFalse(payment._get_blocking_l10n_latam_warning_msg(), "the checks match the net amount")

        payment.action_amount_from_checks()
        self.assertEqual(payment.amount, 1000.0)
