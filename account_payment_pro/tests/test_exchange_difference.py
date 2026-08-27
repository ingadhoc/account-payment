from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestExchangeDifference(TransactionCase):
    """Diferencia de cambio automática al cobrar/pagar una factura en moneda
    extranjera a un TC distinto del de la factura.

    FCP-R07 (cliente) / FCP-R08 (pago a proveedor, su espejo — D3): factura USD
    1.000 al TC 1.000 ($1.000.000), cobrada/pagada al TC 1.100 ($1.100.000). La
    diferencia ($100.000) tiene que salir en su propia cuenta de resultado, separada
    del importe cobrado/pagado, dejando el saldo en cero en ambas monedas.

    Usa como "moneda extranjera" una distinta de la de la compañía activa
    (``env.company``), sea cual sea esa compañía — el escenario no depende de
    ninguna localización en particular, solo de que existan dos monedas.
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
        # tercera cotización, de una "conciliación de la transitoria" posterior al cobro (E4):
        # tiene que existir en el sistema sin afectar la diferencia ya asentada al TC del cobro.
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-03-01", "rate": 1.0 / 1200.0}
        )

        cls.customer = cls.env["res.partner"].create({"name": "Test Exchange Difference Customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Test Exchange Difference Vendor"})
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )

    def _create_move(self, partner, move_type, date="2026-01-01"):
        account_type = "income" if move_type == "out_invoice" else "expense"
        account = self.env["account.account"].search(
            [("account_type", "=", account_type), ("company_ids", "=", self.company.id)], limit=1
        )
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_date": date,
                "company_id": self.company.id,
                "currency_id": self.usd.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test exchange difference line",
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

    def _pay(self, partner, partner_type, payment_type, debt_lines, date, amount=1000.0, accounting_rate=None):
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": partner.id,
                "partner_type": partner_type,
                "payment_type": payment_type,
                "date": date,
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )
        payment.amount = amount
        if accounting_rate is not None:
            payment.accounting_rate = accounting_rate
        return payment

    def test_higher_rate_at_collection_books_a_gain(self):
        """Cobro al TC 1.100 (mayor que el TC 1.000 de la factura): el importe en
        pesos es $1.100.000, la diferencia de $100.000 es una GANANCIA, y la
        factura queda en cero en ambas monedas.

        Cubre FCP-R07-E1 (base).
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self._pay(self.customer, "customer", "inbound", debt, "2026-02-01")
        payment.action_post()

        with self.subTest("el importe en pesos es al TC del cobro"):
            liquidity = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.outstanding_account_id
            )
            self.assertEqual(liquidity.balance, 1100000.0)
        with self.subTest("la diferencia es una ganancia, en su propia cuenta"):
            fx_lines = self._fx_lines(payment)
            self.assertEqual(fx_lines.balance, -100000.0, "un crédito en la cuenta de resultado: ganancia")
        with self.subTest("la factura queda en cero en las dos monedas"):
            self.assertEqual(invoice.amount_residual, 0.0)
            self.assertEqual(invoice.amount_residual_signed, 0.0)

    def test_lower_rate_at_collection_books_a_loss(self):
        """Cobro al TC 900 (menor que el TC 1.000 de la factura): la diferencia de
        $100.000 es una PÉRDIDA, con los mismos ceros de saldo.

        Cubre FCP-R07-E2.
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self._pay(self.customer, "customer", "inbound", debt, "2026-02-15")
        payment.action_post()

        liquidity = payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id)
        self.assertEqual(liquidity.balance, 900000.0)
        fx_lines = self._fx_lines(payment)
        self.assertEqual(fx_lines.balance, 100000.0, "un débito en la cuenta de resultado: pérdida")
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_manual_rate_overrides_the_automatic_one(self):
        """TC fijado a mano en el pago (1.050), distinto del cargado (1.100 para
        esa fecha): el manual manda para el importe en pesos ($1.050.000) y la
        diferencia ($50.000).

        Cubre FCP-R07-E3 (AS5-010).
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self._pay(self.customer, "customer", "inbound", debt, "2026-02-01", accounting_rate=1.0 / 1050.0)
        payment.action_post()

        liquidity = payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id)
        self.assertEqual(liquidity.balance, 1050000.0, "el TC manual manda, no el automático de la fecha")
        fx_lines = self._fx_lines(payment)
        self.assertEqual(fx_lines.balance, -50000.0)

    def test_a_later_reconciliation_rate_does_not_alter_the_difference_already_booked(self):
        """Tres fechas, tres TC: factura al 1.000, cobro al 1.100, y una tercera
        cotización (1.200) ya cargada en el sistema para una fecha posterior — de
        una eventual conciliación de la cuenta transitoria. La diferencia se
        calcula contra el TC del cobro, no contra esa tercera cotización: nada de
        los $100.000 que daría el TC 1.200 entra al asiento.

        Cubre FCP-R07-E4.
        """
        invoice = self._create_move(self.customer, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self._pay(self.customer, "customer", "inbound", debt, "2026-02-01")
        payment.action_post()

        fx_lines = self._fx_lines(payment)
        self.assertEqual(
            fx_lines.balance, -100000.0, "la diferencia es la del TC del cobro (1.100), no la del TC 1.200 posterior"
        )
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_vendor_payment_mirror_also_books_the_difference_to_results(self):
        """Espejo en compras (FCP-R08-E1): pago a proveedor al TC 1.100 sobre una
        factura al TC 1.000 — la diferencia ($100.000) va completa a resultado, el
        mayor del proveedor queda en cero y la factura pagada.
        """
        bill = self._create_move(self.vendor, "in_invoice")
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self._pay(self.vendor, "supplier", "outbound", debt, "2026-02-01")
        payment.action_post()

        liquidity = payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id)
        self.assertEqual(liquidity.balance, -1100000.0)
        fx_lines = self._fx_lines(payment)
        self.assertEqual(fx_lines.balance, 100000.0, "pagar más caro en pesos es una pérdida")
        self.assertEqual(bill.amount_residual, 0.0)
        self.assertEqual(self.company.currency_id.round(sum(bill.line_ids.mapped("amount_residual"))), 0.0)
