"""Tests para el flujo pay_now_journal_id ("Diario de pago directo") del modelo
account.move.

Regresión cubierta:
En v19 el refactor tri-currency cambio _compute_selected_debt para calcular el
signo a partir de payment_type en lugar de partner_type. El codigo original de
pay_now() creaba el account.payment con payment_type="inbound" hardcodeado y lo
flipeaba despues a "outbound" segun el signo de payment_difference; en v19 ese
flip nunca se activaba para in_invoice / in_refund, quedando un asiento
invertido no reconciliable. Estos tests garantizan que los cuatro move_types
generen pagos con payment_type correcto, asiento con el lado correcto, y
factura en payment_state=paid tras el action_post.

Regresión cubierta (multimoneda):
pay_now() copiaba payment_difference, que está en la moneda de la deuda, a
amount, que está en la moneda del pago, sin convertirla. Con el diario de pago
en una moneda distinta a la de la deuda, el pago salía por un importe sin
sentido: la factura quedaba parcial (factura en moneda extranjera y diario en
moneda de la compañía) o sobrepagada (al revés). Estos tests verifican moneda e
importe del pago en ambos sentidos.
"""

from odoo import Command, fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestPayNowJournal(common.TransactionCase):
    # move_type -> (payment_type, partner_type, account_type de la contrapartida)
    _PAY_NOW_EXPECTED = {
        "in_invoice": ("outbound", "supplier", "liability_payable"),
        "out_invoice": ("inbound", "customer", "asset_receivable"),
        "in_refund": ("inbound", "supplier", "liability_payable"),
        "out_refund": ("outbound", "customer", "asset_receivable"),
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        cls.pay_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )
        assert cls.pay_journal, "Se necesita un journal type=bank en la compañía"
        assert cls.sale_journal, "Se necesita un journal type=sale en la compañía"
        assert cls.purchase_journal, "Se necesita un journal type=purchase en la compañía"

        # Para métodos manuales, usar la cuenta default del diario (no outstanding).
        # Con outstanding, Odoo deja el pago como "in_payment" hasta que se concilie
        # con un extracto bancario — lo que invalidaría los asserts de payment_state.
        for pml in cls.pay_journal.inbound_payment_method_line_ids:
            if pml.payment_method_id.code == "manual":
                pml.payment_account_id = cls.pay_journal.default_account_id
        for pml in cls.pay_journal.outbound_payment_method_line_ids:
            if pml.payment_method_id.code == "manual":
                pml.payment_account_id = cls.pay_journal.default_account_id

        ar = cls.env.ref("base.ar", raise_if_not_found=False)
        partner_vals = {"name": "Pay Now Partner"}
        if ar:
            partner_vals["country_id"] = ar.id
        cls.partner = cls.env["res.partner"].create(partner_vals)
        cls.product = cls.env.ref("product.product_product_16")

        # Moneda extranjera a 1.000 unidades de la moneda de la compañía, sea cual
        # sea esa moneda. Los diarios de pago multimoneda se crean acá para no
        # modificar diarios existentes.
        cls.foreign_currency = cls.env.ref("base.EUR")
        if cls.foreign_currency == cls.company.currency_id:
            cls.foreign_currency = cls.env.ref("base.USD")
        cls.foreign_currency.active = True
        cls.env["res.currency.rate"].create(
            {
                "currency_id": cls.foreign_currency.id,
                "company_id": cls.company.id,
                "name": cls.today,
                "rate": 1.0 / 1000.0,
            }
        )
        cls.company_currency_journal = cls._create_pay_journal("PNCC")
        cls.foreign_currency_journal = cls._create_pay_journal("PNFX", cls.foreign_currency)

    @classmethod
    def _create_pay_journal(cls, code, currency=None):
        """Crea un diario de pago propio del test. Los métodos manuales usan la
        cuenta default del diario para que la factura quede paid y no in_payment."""
        journal = cls.env["account.journal"].create(
            {
                "name": f"Pay Now {code}",
                "code": code,
                "type": "bank",
                "company_id": cls.company.id,
                "currency_id": currency.id if currency else False,
            }
        )
        for pml in journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids:
            if pml.payment_method_id.code == "manual":
                pml.payment_account_id = journal.default_account_id
        return journal

    def _make_invoice(self, move_type, journal, currency=None, pay_journal=None):
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner.id,
                "invoice_date": self.today,
                "move_type": move_type,
                "journal_id": journal.id,
                "company_id": self.company.id,
                "currency_id": (currency or journal.currency_id or self.company.currency_id).id,
                "pay_now_journal_id": (pay_journal or self.pay_journal).id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "tax_ids": False,
                        }
                    ),
                ],
            }
        )
        return invoice

    def _assert_reconciled(self, invoice, expected_payment_type, expected_partner_type, expected_account_type):
        """Verifica que la factura quedo paid y el pago asociado tiene el
        payment_type esperado con el asiento correctamente reconciliado."""
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.payment_state, "paid", f"Invoice {invoice.move_type} should be paid")
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(len(invoice.matched_payment_ids), 1)
        payment = invoice.matched_payment_ids
        self.assertEqual(payment.payment_type, expected_payment_type)
        self.assertEqual(payment.partner_type, expected_partner_type)
        self.assertTrue(payment.is_reconciled, "Payment should be fully reconciled")

        # Las lineas del payment sobre la cuenta AP/AR deben quedar reconciliadas.
        # Puede haber mas de una si hay diferencia de cambio / write-off, por eso
        # validamos con all() para no caer en Expected singleton.
        counterpart_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == expected_account_type
        )
        self.assertTrue(counterpart_line, "Payment should have a counterpart line on AP/AR account")
        self.assertTrue(
            all(counterpart_line.mapped("reconciled")),
            "All AP/AR counterpart lines should be reconciled",
        )

    def test_pay_now_in_invoice(self):
        """Factura de proveedor: pago outbound, Dr Payables / Cr Liquidity."""
        invoice = self._make_invoice("in_invoice", self.purchase_journal)
        invoice.action_post()
        self._assert_reconciled(invoice, "outbound", "supplier", "liability_payable")

    def test_pay_now_out_invoice(self):
        """Factura de cliente: pago inbound, Dr Liquidity / Cr Receivables."""
        invoice = self._make_invoice("out_invoice", self.sale_journal)
        invoice.action_post()
        self._assert_reconciled(invoice, "inbound", "customer", "asset_receivable")

    def test_pay_now_in_refund(self):
        """NC de proveedor: pago inbound (el proveedor te devuelve)."""
        invoice = self._make_invoice("in_refund", self.purchase_journal)
        invoice.action_post()
        self._assert_reconciled(invoice, "inbound", "supplier", "liability_payable")

    def test_pay_now_out_refund(self):
        """NC de cliente: pago outbound (le devolves al cliente)."""
        invoice = self._make_invoice("out_refund", self.sale_journal)
        invoice.action_post()
        self._assert_reconciled(invoice, "outbound", "customer", "asset_receivable")

    def _check_pay_now_amount(self, move_type, currency, pay_journal, expected_amount):
        """Postea una factura con pay_now y verifica que quede paid con un pago en
        la moneda del diario por expected_amount."""
        payment_type, partner_type, account_type = self._PAY_NOW_EXPECTED[move_type]
        journal = self.purchase_journal if move_type.startswith("in_") else self.sale_journal
        pay_currency = pay_journal.currency_id or self.company.currency_id
        invoice = self._make_invoice(move_type, journal, currency, pay_journal)
        invoice.action_post()
        self._assert_reconciled(invoice, payment_type, partner_type, account_type)
        payment = invoice.matched_payment_ids
        self.assertEqual(payment.currency_id, pay_currency, "El pago debe quedar en la moneda del diario")
        self.assertEqual(
            pay_currency.compare_amounts(payment.amount, expected_amount),
            0,
            f"Importe del pago: {payment.amount} {pay_currency.name}, se esperaba {expected_amount}",
        )

    def test_pay_now_foreign_invoice_company_currency_journal(self):
        """Factura en moneda extranjera, diario en moneda de la compañía: el pago
        es el total convertido (100 x 1.000), no el total en moneda extranjera."""
        for move_type in self._PAY_NOW_EXPECTED:
            with self.subTest(move_type=move_type):
                self._check_pay_now_amount(move_type, self.foreign_currency, self.company_currency_journal, 100000.0)

    def test_pay_now_company_invoice_foreign_currency_journal(self):
        """Factura en moneda de la compañía, diario en moneda extranjera: el pago
        es el total convertido (100 / 1.000), sin sobrepago."""
        self._check_pay_now_amount("in_invoice", self.company.currency_id, self.foreign_currency_journal, 0.1)

    def test_pay_now_same_foreign_currency(self):
        """Factura y diario en la misma moneda extranjera: el pago es el total de
        la factura, sin conversión."""
        self._check_pay_now_amount("in_invoice", self.foreign_currency, self.foreign_currency_journal, 100.0)
