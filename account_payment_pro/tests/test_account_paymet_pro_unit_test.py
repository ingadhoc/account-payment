from datetime import timedelta

from odoo import Command, fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestAccountPaymentProUnitTest(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.company = self.env.company
        self.company_bank_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "bank")], limit=1
        )
        self.company_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "sale")], limit=1
        )
        self.company.use_payment_pro = True

        self.eur_currency = self.env["res.currency"].with_context(active_test=False).search([("name", "=", "EUR")])
        self.eur_currency.active = True
        self.rates = self.env["res.currency.rate"].create(
            [
                {
                    "name": "2024-01-01",
                    "inverse_company_rate": 800,
                    "currency_id": self.eur_currency.id,
                    "company_id": self.company.id,
                },
                {
                    "name": (self.today - timedelta(days=10)).strftime("%Y-%m-%d"),
                    "inverse_company_rate": 1000,
                    "currency_id": self.eur_currency.id,
                    "company_id": self.company.id,
                },
            ]
        )
        ar = ar = self.env.ref("base.ar")
        self.partner_ri = self.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))

    def test_create_payment_with_a_date_rate_then_change_rate(self):
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today - timedelta(days=14),
                "move_type": "out_invoice",
                "journal_id": self.company_journal.id,
                "company_id": self.company.id,
                "currency_id": self.eur_currency.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 100,
                        }
                    ),
                ],
            }
        )
        invoice.action_post()

        vals = {
            "journal_id": self.company_bank_journal.id,
            "amount": invoice.amount_total,
            "currency_id": self.eur_currency.id,
            "date": self.today - timedelta(days=1),
        }
        action_context = invoice.action_register_payment()["context"]
        payment = self.env["account.payment"].with_context(**action_context).create(vals)
        payment.action_post()
        eur_actual_rate_1 = 1 / invoice.currency_id._get_rates(self.company, self.today).get(self.eur_currency.id)

        self.assertEqual(payment.exchange_rate, eur_actual_rate_1, "no se tomo de forma correcta el tipo de cambio")
        self.rates[1].inverse_company_rate = 2000
        eur_actual_rate_2 = 1 / invoice.currency_id._get_rates(self.company, self.today).get(self.eur_currency.id)
        self.assertNotEqual(
            payment.exchange_rate,
            eur_actual_rate_2,
            "Se tomo de forma incorrecta el tipo de cambio en un pago ya posteado",
        )
        self.assertEqual(payment.exchange_rate, eur_actual_rate_1, "no se tomo de forma correcta el tipo de cambio")

        payment.action_draft()
        payment.date = self.today
        payment.action_post()
        self.assertEqual(payment.exchange_rate, eur_actual_rate_2, "no se tomo de forma correcta el tipo de cambio")

    def test_force_amount_company_currency_without_payment_pro(self):
        """Test that force_amount_company_currency is used in liquidity lines when use_payment_pro is False"""
        # Disable payment_pro for this test
        self.company.use_payment_pro = False

        # Use EUR currency (assumes company currency is USD or different from EUR)
        # EUR is already configured in setUp()
        payment_amount_eur = 100.0
        expected_normal_conversion = 100000.0  # 100 * 1000 (rate from setUp)
        forced_amount = 5000.0  # Different from normal conversion

        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_ri.id,
                "journal_id": self.company_bank_journal.id,
                "amount": payment_amount_eur,
                "currency_id": self.eur_currency.id,
                "date": self.today,
            }
        )

        # Verify normal conversion is calculated
        self.assertAlmostEqual(
            payment.amount_company_currency,
            expected_normal_conversion,
            places=2,
            msg="Amount should be converted normally without force_amount_company_currency",
        )

        # Set forced amount
        payment.force_amount_company_currency = forced_amount

        # Verify force_amount_company_currency is used
        self.assertEqual(
            payment.amount_company_currency,
            forced_amount,
            "Amount should use force_amount_company_currency when set",
        )

        # Post payment and check liquidity lines
        payment.action_post()

        # Get liquidity lines
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )

        # Verify liquidity line balance uses forced amount
        liquidity_balance = sum(liquidity_lines.mapped("balance"))
        self.assertAlmostEqual(
            liquidity_balance,
            forced_amount,
            places=2,
            msg=f"Liquidity line balance should be {forced_amount} (forced), not {expected_normal_conversion} (normal conversion)",
        )

        # Verify amount_company_currency_signed_pro also uses forced amount
        self.assertEqual(
            payment.amount_company_currency_signed_pro,
            forced_amount,
            "amount_company_currency_signed_pro should use forced amount",
        )

        # Test that changes still preserve forced amount (synchronization)
        payment.action_draft()
        payment.memo = "Test synchronization"
        payment.action_post()

        # Verify liquidity lines still use forced amount after synchronization
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )
        liquidity_balance = sum(liquidity_lines.mapped("balance"))
        self.assertAlmostEqual(
            liquidity_balance,
            forced_amount,
            places=2,
            msg="Liquidity line balance should still use forced amount after synchronization",
        )

    def test_posted_payment_without_payment_pro_keeps_accounting_rate_after_rate_change(self):
        self.company.use_payment_pro = False

        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_ri.id,
                "journal_id": self.company_bank_journal.id,
                "amount": 100.0,
                "currency_id": self.eur_currency.id,
                "date": self.today,
            }
        )
        payment.action_post()

        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )
        accounting_amount = abs(sum(liquidity_lines.mapped("balance")))
        self.assertAlmostEqual(accounting_amount, 100000.0, places=2)
        self.assertAlmostEqual(payment.amount_company_currency, accounting_amount, places=2)
        self.assertAlmostEqual(payment.exchange_rate, 1000.0, places=2)

        self.rates[1].inverse_company_rate = 2000
        payment.invalidate_recordset(["amount_company_currency", "exchange_rate"])

        self.assertAlmostEqual(payment.amount_company_currency, accounting_amount, places=2)
        self.assertAlmostEqual(payment.exchange_rate, 1000.0, places=2)

    def test_write_off_line_amounts_company_vs_payment_currency(self):
        """Minimal test: company currency vs payment currency, force company amount and check write-off line balance"""
        # Use existing company and ensure we have a different currency for the payment
        company_currency = self.company.currency_id

        # Use USD as payment currency (different from company currency)
        usd = self.env["res.currency"].with_context(active_test=False).search([("name", "=", "USD")], limit=1)
        usd.active = True

        # If company already uses USD, skip test since we need different currencies
        if company_currency == usd:
            self.skipTest("Test requires payment currency different from company currency")

        # create payment in USD but force company amount so exchange_rate = 1300
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_ri.id,
                "journal_id": self.company_bank_journal.id,
                "company_id": self.company.id,
                "amount": 1.0,
                "currency_id": usd.id,
                "force_amount_company_currency": 1300.0,
            }
        )

        # Create a dedicated account for write-off to avoid conflicts with payment accounts
        write_off_account = self.env["account.account"].create(
            {
                "name": "Write-Off Test Account",
                "code": "WOTEST001",
                "account_type": "expense",
                "company_id": self.company.id,
            }
        )
        wot = self.env["account.write_off.type"].create(
            {
                "name": "WOT Test",
                "label": "WOT Test",
                "company_ids": [(6, 0, [self.company.id])],
                "account_id": write_off_account.id,
            }
        )

        payment.write_off_type_id = wot
        payment.write_off_amount = 1000.0

        payment.action_post()

        write_off_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id == wot.account_id)
        self.assertTrue(write_off_lines, "No write-off move line found")
        self.assertEqual(len(write_off_lines), 1, "Expected exactly one write-off move line")

        line = write_off_lines[0]
        expected_amount_currency = 1000.0 / 1300.0
        expected_balance = 1000.0

        self.assertAlmostEqual(
            float(line.amount_currency or 0.0),
            expected_amount_currency,
            places=6,
            msg="amount_currency on write-off line is incorrect",
        )
        self.assertAlmostEqual(
            float(line.balance),
            expected_balance,
            places=2,
            msg="balance on write-off line should be the write_off_amount in company currency",
        )
