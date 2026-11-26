from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestExchangeDifferencePartial(AccountInvariantsMixin, TransactionCase):
    """Diferencia de cambio proporcional en cobros parciales, control negativo, y
    el excedente de un pago de más que no se pierde al convertir.

    FCP-R07-E6/E7/E9, FCP-R08-E7.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        cls.usd = cls.env.ref("base.EUR")
        if cls.usd == cls.company.currency_id:
            cls.usd = cls.env.ref("base.USD")
        cls.usd.active = True
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-01-01", "rate": 0.001}
        )
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-02-01", "rate": 1.0 / 1100.0}
        )
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-02-15", "rate": 1.0 / 900.0}
        )

        cls.customer = cls.env["res.partner"].create({"name": "Test Exchange Partial Customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Test Exchange Partial Vendor"})
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )

    def _create_move(self, partner, move_type):
        account_type = "income" if move_type == "out_invoice" else "expense"
        account = self.env["account.account"].search(
            [("account_type", "=", account_type), ("company_ids", "=", self.company.id)], limit=1
        )
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_date": "2026-01-01",
                "company_id": self.company.id,
                "currency_id": self.usd.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test exchange partial line",
                            "quantity": 1,
                            "price_unit": 1000.0,
                            "account_id": account.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        move.action_post()
        return move

    def _fx_lines(self, payment):
        """Líneas de diferencia de cambio: no se identifican por un
        ``account_type`` fijo (varía según el plan de cuentas de la
        compañía), sino por ser las cuentas de ganancia/pérdida por cambio
        configuradas en la propia compañía."""
        fx_accounts = (
            self.company.income_currency_exchange_account_id | self.company.expense_currency_exchange_account_id
        )
        return payment.exchange_diff_move_ids.line_ids.filtered(lambda line: line.account_id in fx_accounts)

    def test_partial_collection_generates_a_proportional_difference(self):
        """Cobro parcial de USD 400 (de una factura de USD 1.000) al TC 1.100: la
        diferencia es proporcional a lo cobrado ($40.000, no los $100.000 de la
        factura completa), y el saldo restante (USD 600) queda abierto.

        Cubre FCP-R07-E6.
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.customer.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "date": "2026-02-01",
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
                "unreconciled_amount": -600.0,
            }
        )
        self.assertEqual(payment.to_pay_amount, 400.0)
        payment.amount = 400.0
        payment.action_post()
        self.assert_payment_invariants(payment, "cobro parcial")

        self.assertEqual(invoice.amount_residual, 600.0, "el resto queda abierto en USD")
        fx_lines = self._fx_lines(payment)
        self.assertEqual(fx_lines.balance, -40000.0, "la diferencia es proporcional a lo cobrado, no al total")

    def test_two_partial_collections_at_different_rates_each_book_their_own_difference(self):
        """Dos cobros parciales a TC distintos (USD 400 al 1.100, luego USD 600 al
        900): cada uno genera su propia diferencia — ganancia el primero, pérdida
        el segundo — y el saldo final cierra en cero en ambas monedas.

        Cubre FCP-R07-E7.
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment_1 = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.customer.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "date": "2026-02-01",
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
                "unreconciled_amount": -600.0,
            }
        )
        payment_1.amount = 400.0
        payment_1.action_post()
        self.assert_payment_invariants(payment_1, "primer cobro parcial")

        debt_remaining = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
        )
        payment_2 = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.customer.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "date": "2026-02-15",
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt_remaining.ids)],
            }
        )
        self.assertEqual(payment_2.to_pay_amount, 600.0)
        payment_2.amount = 600.0
        payment_2.action_post()
        self.assert_payment_invariants(payment_2, "segundo cobro parcial")

        with self.subTest("cada cobro tiene su propia diferencia, con signos opuestos"):
            fx_1 = self._fx_lines(payment_1)
            fx_2 = self._fx_lines(payment_2)
            self.assertEqual(fx_1.balance, -40000.0, "ganancia en el primer cobro")
            self.assertEqual(fx_2.balance, 60000.0, "pérdida en el segundo")

        with self.subTest("el saldo final cierra en cero en las dos monedas"):
            self.assertEqual(invoice.amount_residual, 0.0)
            self.assertEqual(self.company.currency_id.round(sum(invoice.line_ids.mapped("amount_residual"))), 0.0)

    def test_negative_control_same_currency_same_rate_generates_no_difference_line(self):
        """Control negativo: cobro en USD contra una factura en USD, mismo
        importe y mismo TC (el diario de banco también en USD, sin cambio de
        fecha) — no se genera ninguna línea de diferencia de cambio donde no hay
        variación real.

        Cubre FCP-R07-E9 (AS7-006): el bug histórico era que aparecía diferencia
        donde no había ninguna.
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        usd_bank = self.env["account.journal"].create(
            {
                "name": "Test Bank USD Negative Control",
                "type": "bank",
                "code": "TBKNC",
                "currency_id": self.usd.id,
                "company_id": self.company.id,
            }
        )
        payment = self.env["account.payment"].create(
            {
                "journal_id": usd_bank.id,
                "partner_id": self.customer.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "date": "2026-01-01",
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        payment.amount = 1000.0
        payment.action_post()
        self.assert_payment_invariants(payment, "control negativo, misma moneda mismo TC")

        self.assertFalse(payment.exchange_diff_move_ids)
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_overpaying_in_foreign_currency_keeps_the_excess_in_that_currency(self):
        """Pago de más: USD 1.100 sobre una factura de USD 1.000 — la factura
        queda pagada y los USD 100 de excedente quedan a cuenta del proveedor
        expresados en USD, no convertidos a pesos y perdidos en el camino.

        Cubre FCP-R08-E7.
        """
        bill = self._create_move(self.vendor, "in_invoice")
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": "2026-02-01",
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        payment.amount = 1100.0
        self.assertEqual(payment.payment_difference, -100.0)
        payment.action_post()
        self.assert_payment_invariants(payment, "pago de más en moneda extranjera")

        self.assertEqual(bill.amount_residual, 0.0)
        open_lines = self.env["account.move.line"].search(
            [
                ("partner_id", "=", self.vendor.id),
                ("account_id.account_type", "=", "liability_payable"),
                ("reconciled", "=", False),
            ]
        )
        self.assertEqual(len(open_lines), 1)
        self.assertEqual(open_lines.currency_id, self.usd, "el excedente sigue expresado en dólares")
        self.assertEqual(open_lines.amount_residual_currency, 100.0)
