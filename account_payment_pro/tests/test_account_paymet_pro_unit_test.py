from datetime import timedelta

from odoo import Command, fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestAccountPaymentProUnitTest(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super(TestAccountPaymentProUnitTest, cls).setUpClass()
        cls.today = fields.Date.today()
        cls.ar = ar = cls.env.ref("base.ar")

        cls.company = cls.env.company
        cls.company_bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        cls.company_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.company.use_payment_pro = True
        cls.eur_currency = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "EUR")])
        cls.eur_currency.active = True
        cls.rates = cls.env["res.currency.rate"].create(
            [
                {
                    "name": "2024-01-01",
                    "inverse_company_rate": 800,
                    "currency_id": cls.eur_currency.id,
                    "company_id": cls.company.id,
                },
                {
                    "name": (cls.today - timedelta(days=10)).strftime("%Y-%m-%d"),
                    "inverse_company_rate": 1000,
                    "currency_id": cls.eur_currency.id,
                    "company_id": cls.company.id,
                },
            ]
        )
        cls.partner_ri = cls.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))

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
        # accounting_rate = _get_conversion_rate(from=company_currency=ARS, to=EUR)
        # formato Odoo nativo: ej. 0.001 para "1 EUR = 1000 ARS"
        # El pago tiene date=today-1, por lo que aplica la tasa de today-10 (inverse_company_rate=1000)
        expected_rate_1 = self.env["res.currency"]._get_conversion_rate(
            from_currency=self.company.currency_id,
            to_currency=self.eur_currency,
            company=self.company,
            date=payment.date,
        )
        self.assertEqual(payment.accounting_rate, expected_rate_1, "no se tomo de forma correcta el tipo de cambio")
        self.rates[1].inverse_company_rate = 2000
        expected_rate_2 = self.env["res.currency"]._get_conversion_rate(
            from_currency=self.company.currency_id,
            to_currency=self.eur_currency,
            company=self.company,
            date=payment.date,
        )
        self.assertNotEqual(
            payment.accounting_rate,
            expected_rate_2,
            "Se tomo de forma incorrecta el tipo de cambio en un pago ya posteado",
        )
        self.assertEqual(payment.accounting_rate, expected_rate_1, "no se tomo de forma correcta el tipo de cambio")

        payment.action_draft()
        payment.date = self.today
        payment._compute_accounting_rate()
        payment.action_post()
        expected_rate_today = self.env["res.currency"]._get_conversion_rate(
            from_currency=self.company.currency_id,
            to_currency=self.eur_currency,
            company=self.company,
            date=self.today,
        )
        self.assertEqual(payment.accounting_rate, expected_rate_today, "no se tomo de forma correcta el tipo de cambio")
