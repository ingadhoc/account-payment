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
<<<<<<< 43898b18227c28f001812cb3a322156152b5f6bc
        cls.partner_ri = cls.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))
||||||| 9e638231f558984f00385106f1b89101719fbb49

        self.partner_ri = self.env["res.partner"].search([("name", "=", "Deco Addict")], limit=1)
=======
        ar = ar = self.env.ref("base.ar")
        self.partner_ri = self.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))
>>>>>>> d8127e0c24589714192d2ff7f184d0f2989ba4b7

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
        payment._compute_amount_company_currency()
        payment.action_post()
        self.assertEqual(payment.exchange_rate, eur_actual_rate_2, "no se tomo de forma correcta el tipo de cambio")
