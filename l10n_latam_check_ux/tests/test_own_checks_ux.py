##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestOwnChecksUx(TransactionCase):
    """Own checks build one liquidity line per check (no post-hoc split move),
    reproduced from l10n_latam_check_ux instead of a core patch."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        own_checks = cls.env.ref("l10n_latam_check.account_payment_method_own_checks")
        # reuse a company/journal that already has own checks configured
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [
                ("payment_method_id", "=", own_checks.id),
                ("payment_account_id", "!=", False),
            ],
            limit=1,
        )
        if not cls.payment_method_line:
            raise cls.skipTest(cls, "No own_checks journal configured in this database")
        cls.bank_journal = cls.payment_method_line.journal_id
        cls.company = cls.bank_journal.company_id
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.partner = cls.env["res.partner"].create({"name": "Own Check Vendor"})

    def _create_own_check_payment(self, amounts, currency=None):
        return (
            self.env["account.payment"]
            .with_company(self.company)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": self.partner.id,
                    "journal_id": self.bank_journal.id,
                    "company_id": self.company.id,
                    "date": fields.Date.today(),
                    "currency_id": (currency or self.company.currency_id).id,
                    "payment_method_line_id": self.payment_method_line.id,
                    "l10n_latam_new_check_ids": [
                        Command.create({"payment_date": fields.Date.today(), "amount": amount}) for amount in amounts
                    ],
                }
            )
        )

    def test_one_liquidity_line_per_check(self):
        payment = self._create_own_check_payment([25, 25])
        payment.action_post()
        self.assertEqual(payment.amount, 50)
        outstanding_lines = payment.l10n_latam_new_check_ids.mapped("outstanding_line_id")
        self.assertEqual(len(outstanding_lines), 2, "There should be a liquidity line per check.")

    def test_no_separate_split_move(self):
        payment = self._create_own_check_payment([20, 30, 70])
        payment.action_post()
        self.assertEqual(payment.amount, 120)
        # every check points to a line inside the payment move, not a separate one
        for check in payment.l10n_latam_new_check_ids:
            self.assertEqual(check.outstanding_line_id.move_id, payment.move_id)

    def test_reset_to_draft_keeps_checks_linked(self):
        payment = self._create_own_check_payment([20, 30, 70])
        payment.action_post()
        payment.action_draft()
        # no separate split move to unlink, so checks stay linked to the payment move
        for check in payment.l10n_latam_new_check_ids:
            self.assertEqual(check.outstanding_line_id.move_id, payment.move_id)

    def test_own_check_multicurrency_liquidity_amounts(self):
        """Own checks in a currency different from the company one: each check
        line keeps the nominal in amount_currency and its conversion in balance.
        The issue only shows up when the rate is not 1:1."""
        company_currency = self.company.currency_id
        foreign_currency = self.env.ref("base.EUR")
        if foreign_currency == company_currency:
            foreign_currency = self.env.ref("base.USD")
        foreign_currency.active = True
        self.env["res.currency.rate"].create(
            {
                "name": fields.Date.today(),
                "currency_id": foreign_currency.id,
                "company_id": self.company.id,
                "rate": 4.0,
            }
        )
        payment = self._create_own_check_payment([20, 30, 70], currency=foreign_currency)
        payment.action_post()
        self.assertEqual(payment.amount, 120)

        for check in payment.l10n_latam_new_check_ids:
            line = check.outstanding_line_id
            self.assertEqual(
                abs(line.amount_currency),
                check.amount,
                "Check liquidity line must hold the nominal in the payment currency",
            )
            expected_balance = foreign_currency._convert(check.amount, company_currency, self.company, payment.date)
            self.assertEqual(
                abs(line.balance),
                expected_balance,
                "Check liquidity line balance must be the nominal converted to company currency",
            )
