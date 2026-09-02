from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestExchangeDifferenceEdgeCases(AccountInvariantsMixin, TransactionCase):
    """Diferencia de cambio: diario en la misma moneda, combinación de documentos,
    y una tercera moneda de por medio.

    FCP-R07-E5 / FCP-R08-E2 (espejo): pagar desde un diario en la MISMA moneda de
    la factura, sin que haya pasado tiempo/cotización de por medio, no genera
    ninguna diferencia de cambio — ni en la moneda extranjera ni en pesos.
    FCP-R08-E5/E6: cada documento conserva su propia cotización, y una tercera
    moneda hace la doble conversión una sola vez.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        # Dos monedas "extranjeras" (factura y banco) distintas entre sí y de la
        # de la compañía, sea cual sea — el escenario no depende de ninguna
        # localización en particular, solo de que existan tres monedas.
        candidates = (
            cls.env["res.currency"].with_context(active_test=False).search([("name", "in", ["USD", "EUR", "GBP"])])
        )
        others = candidates.filtered(lambda c: c != cls.company.currency_id)
        cls.usd, cls.eur = others[0], others[1]
        (cls.usd + cls.eur).active = True

        # misma cotización en ambas fechas: representa "sin conversión" (E2/E5 de R07/R08)
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-01-01", "rate": 0.001}
        )
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-02-01", "rate": 0.001}
        )
        # segunda cotización distinta, solo para la NC de FCP-R08-E5 (conserva su propio TC)
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-01-15", "rate": 1.0 / 1200.0}
        )
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.eur.id, "company_id": cls.company.id, "name": "2026-02-01", "rate": 1.0 / 1300.0}
        )

        cls.vendor = cls.env["res.partner"].create({"name": "Test Exchange Edge Cases Vendor"})
        cls.expense = cls.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "=", cls.company.id)], limit=1
        )

    def _create_bill(self, amount, invoice_date="2026-01-01", move_type="in_invoice"):
        bill = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.vendor.id,
                "invoice_date": invoice_date,
                "company_id": self.company.id,
                "currency_id": self.usd.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test exchange edge case line",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": self.expense.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def test_paying_from_a_journal_in_the_same_currency_with_no_rate_change_has_no_exchange_difference(self):
        """Pago desde un diario en USD, sin que la cotización se haya movido entre
        la factura y el pago: sin diferencia de cambio, saldo cero en ambas
        monedas.

        Cubre FCP-R07-E5 / FCP-R08-E2.
        """
        bill = self._create_bill(1000.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        usd_bank = self.env["account.journal"].create(
            {
                "name": "Test Bank USD",
                "type": "bank",
                "code": "TBKUS",
                "currency_id": self.usd.id,
                "company_id": self.company.id,
            }
        )
        payment = self.env["account.payment"].create(
            {
                "journal_id": usd_bank.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": "2026-02-01",
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        payment.amount = 1000.0
        payment.action_post()
        self.assert_payment_invariants(payment, "pago sin cambio de cotización")

        self.assertFalse(payment.exchange_diff_move_ids, "sin cotización distinta, no hay nada que revaluar")
        self.assertEqual(bill.amount_residual, 0.0)
        self.assertEqual(self.company.currency_id.round(sum(bill.line_ids.mapped("amount_residual"))), 0.0)

    def test_invoice_and_credit_note_each_keep_their_own_rate_and_the_net_closes_without_duplicating_the_difference(
        self,
    ):
        """Factura USD 1.000 al TC 1.000 y NC USD 200 a otro TC (1.200), pago del
        neto (USD 800): cada documento conserva su propia cotización y el neto
        cierra en USD sin duplicar la diferencia.

        Cubre FCP-R08-E5.
        """
        bill = self._create_bill(1000.0, invoice_date="2026-01-01")
        credit_note = self._create_bill(200.0, invoice_date="2026-01-15", move_type="in_refund")
        debt = (bill | credit_note).line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")

        bank_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "bank")], limit=1
        )
        payment = self.env["account.payment"].create(
            {
                "journal_id": bank_journal.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": "2026-02-01",
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        self.assertEqual(payment.to_pay_amount, 800.0, "la NC ya resta del neto en USD")
        payment.amount = 800.0
        payment.action_post()
        self.assert_payment_invariants(payment, "pago del neto factura+NC a distinto TC cada una")

        self.assertEqual(bill.amount_residual, 0.0)
        self.assertEqual(credit_note.amount_residual, 0.0)

    def test_paying_in_a_third_currency_converts_once_with_no_residual_in_any_currency(self):
        """Factura en USD, pago desde un diario en EUR, compañía en ARS: la doble
        conversión (USD→ARS→EUR) se hace una sola vez, sin residuo en ninguna de
        las tres monedas.

        Cubre FCP-R08-E6 (caso de bancos en CLP/PYG).
        """
        bill = self._create_bill(1000.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        eur_bank = self.env["account.journal"].create(
            {
                "name": "Test Bank EUR",
                "type": "bank",
                "code": "TBKEU",
                "currency_id": self.eur.id,
                "company_id": self.company.id,
            }
        )
        payment = self.env["account.payment"].create(
            {
                "journal_id": eur_bank.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": "2026-02-01",
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        self.assertEqual(payment.counterpart_currency_id, self.usd, "la deuda sigue expresada en USD")
        # payment.amount está en EUR (moneda del diario); to_pay_amount está en USD
        # (moneda de la deuda) — hay que convertir, no asignar el número directo.
        payment.amount = payment.counterpart_currency_id._convert(
            payment.to_pay_amount, payment.currency_id, self.company, payment.date
        )
        payment.action_post()
        # tercera moneda: la línea del banco (EUR) no cierra contra la del
        # comprobante (USD) sin pasar por la de compañía, así que
        # assert_payment_invariants se salta closes_in_both_currencies acá
        # (más de una moneda extranjera en juego) — el residuo cero ya lo
        # verifican los asserts de abajo.
        self.assert_payment_invariants(payment, "pago en una tercera moneda")

        self.assertEqual(bill.amount_residual, 0.0, "sin residuo en USD")
        self.assertEqual(payment.payment_difference, 0.0, "la conversión se hizo una sola vez, sin sobrar ni faltar")
