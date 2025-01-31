import odoo.tests.common as common
from odoo import Command, fields
from datetime import timedelta


class TestAccountPaymentProUnitTest(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.company = self.env.company
        self.company_bank_journal = self.env['account.journal'].search([('company_id', '=', self.company.id), ('type', '=', 'bank')], limit=1) 
        self.company_journal = self.env['account.journal'].search([('company_id', '=', self.company.id), ('type', '=', 'sale')], limit=1)
        self.company.use_payment_pro = True
        
        self.eur_currency = self.env['res.currency'].with_context(active_test=False).search([
            ('name', '=', 'EUR')
        ])
        self.eur_currency.active = True
        self.rates = self.env['res.currency.rate'].create([{
                'name': '2024-01-01',
                'inverse_company_rate': 800,
                'currency_id': self.eur_currency.id,
                'company_id':  self.company.id,
            },
            {
                'name': (self.today - timedelta(days=10)).strftime('%Y-%m-%d'),
                'inverse_company_rate': 1000,
                'currency_id': self.eur_currency.id,
                'company_id':  self.company.id,
            },
        ])

        self.partner_ri = self.env['res.partner'].search([('name', '=', 'Deco Addict')])

    def test_create_payment_with_a_date_rate_then_change_rate(self):
        invoice = self.env['account.move'].create({
            'partner_id': self.partner_ri.id,
            'invoice_date': self.today - timedelta(days=14),
            'move_type': 'out_invoice',
            'journal_id': self.company_journal.id,
            'company_id': self.company.id,
            'currency_id': self.eur_currency.id,
            'invoice_line_ids': [
                Command.create({
                    'product_id': self.env.ref('product.product_product_16').id,
                    'quantity': 1,
                    'price_unit': 100,
                }),
            ],
        })
        invoice.action_post()

        vals = {
            'journal_id': self.company_bank_journal.id,
            'amount': invoice.amount_total,
            'currency_id': self.eur_currency.id,
            'date': self.today - timedelta(days=1),
        }
        action_context = invoice.action_register_payment()['context']
        payment = self.env['account.payment'].with_context(action_context).create(vals)
        payment.action_post()
        eur_actual_rate_1 = 1 / invoice.currency_id._get_rates(self.company, self.today).get(self.eur_currency.id)

        self.assertEqual(payment.exchange_rate, eur_actual_rate_1, "no se tomo de forma correcta el tipo de cambio")
        self.rates[1].inverse_company_rate = 2000
        eur_actual_rate_2 = 1 / invoice.currency_id._get_rates(self.company, self.today).get(self.eur_currency.id)
        self.assertNotEqual(payment.exchange_rate, eur_actual_rate_2, "Se tomo de forma incorrecta el tipo de cambio en un pago ya posteado")
        self.assertEqual(payment.exchange_rate, eur_actual_rate_1, "no se tomo de forma correcta el tipo de cambio")

        payment.action_draft()
        payment.date = self.today
        payment.action_post()
        self.assertEqual(payment.exchange_rate, eur_actual_rate_2, "no se tomo de forma correcta el tipo de cambio")
