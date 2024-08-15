import odoo.tests.common as common
from odoo import Command, fields


class TestAccountPaymentFinancialSurcharge(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.first_company = self.env['res.company'].search([('name', '=', 'Muebleria ARG'),('use_payment_pro','=',True)])
        self.partner_ri = self.env['res.partner'].search([('name', '=', 'ADHOC SA')])

        self.first_company_journal = self.env['account.journal'].search([('company_id', '=', self.first_company.id), ('type', '=', 'bank')], limit=1)                

        installment_dic_1 = {
            'name': 'Plan 1 cuota 10%',
            'installment': 1,
            'divisor': 1,
            'surcharge_coefficient': 1.01
        }
        installment_dic_2 = {
            'name': 'Plan 3 cuotas 30%',
            'installment': 3,
            'divisor': 1,
            'surcharge_coefficient': 1.03
        }
        self.account_card = self.env['account.card'].create({'name':'Visa1', 'installment_ids': [(0, 0, installment_dic_1), (0, 0, installment_dic_2)]})

        manual_payment_method_id = self.env.ref('account.account_payment_method_manual_in').id
        self.card_payment_method = self.env['account.payment.method.line'].create({
            'name': 'Tarjetas',
            'payment_method_id': manual_payment_method_id,
            'journal_id': self.first_company_journal.id,
            })
        self.card_payment_method.available_card_ids = [self.account_card.id]

        self.product_surcharge = self.env.ref('card_installment.product_product_financial')
        self.env['res.config.settings'].search([('company_id', '=', self.first_company.id)]).payment_term_surcharge_product_id = self.product_surcharge.id

    def test_payment_financial_surcharge_1(self):
        invoice = self.env['account.move'].create({
            'partner_id': self.partner_ri.id,
            'date': self.today,
            'move_type': 'out_invoice',
            'journal_id': self.first_company_journal.id,
            'company_id': self.first_company.id,
            'invoice_line_ids': [
                Command.create({
                    'product_id': self.env.ref('product.product_product_16').id,
                    'quantity': 1,
                    'price_unit': 1000,
                }),
            ],
        })

        invoice.action_post()
        original_amount = invoice.amount_total

        vals = {
            'journal_id': self.first_company_journal.id
        }

        action_context = invoice.action_register_payment()['context']
        payment = self.env['account.payment'].with_context(action_context).create(vals)

        payment.write({
            'payment_method_line_id': self.card_payment_method.id,
            'card_id': self.account_card.id,
            'installment_id': self.account_card.installment_ids[0].id
        })

        payment._inverse_net_amount()
        payment.action_post()

        self.assertEqual(round(payment.amount,2), original_amount + payment.financing_surcharge, "Fallo el monto total")
        self.assertEqual(payment.financing_surcharge, payment.matched_move_line_ids[1].balance, "Fallo el monto de la ND por el recargo")

    def test_payment_financial_surcharge_2(self):
        invoice = self.env['account.move'].create({
            'partner_id': self.partner_ri.id,
            'date': self.today,
            'move_type': 'out_invoice',
            'journal_id': self.first_company_journal.id,
            'company_id': self.first_company.id,
            'invoice_line_ids': [
                Command.create({
                    'product_id': self.env.ref('product.product_product_16').id,
                    'quantity': 1,
                    'price_unit': 1000,
                }),
            ],
        })

        invoice.action_post()
        original_amount = invoice.amount_total

        vals = {
            'journal_id': self.first_company_journal.id
        }

        action_context = invoice.action_register_payment()['context']
        payment = self.env['account.payment'].with_context(action_context).create(vals)

        payment.write({
            'payment_method_line_id': self.card_payment_method.id,
            'card_id': self.account_card.id,
            'installment_id': self.account_card.installment_ids[1].id
        })

        payment._inverse_net_amount()
        payment.action_post()

        self.assertEqual(round(payment.amount,2), original_amount + payment.financing_surcharge, "Fallo el monto total")
        self.assertEqual(payment.financing_surcharge, payment.matched_move_line_ids[1].balance, "Fallo el monto de la ND por el recargo")
