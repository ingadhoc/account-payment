"""Tests para el flujo pay_now_journal_id ("Diario de pago directo") del modelo
account.move.

Regresion cubierta:
En v19 el refactor tri-currency cambio _compute_selected_debt para calcular el
signo a partir de payment_type en lugar de partner_type. El codigo original de
pay_now() creaba el account.payment con payment_type="inbound" hardcodeado y lo
flipeaba despues a "outbound" segun el signo de payment_difference; en v19 ese
flip nunca se activaba para in_invoice / in_refund, quedando un asiento
invertido no reconciliable. Estos tests garantizan que los cuatro move_types
generen pagos con payment_type correcto, asiento con el lado correcto, y
factura en payment_state=paid tras el action_post.
"""

from odoo import Command, fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestPayNowJournal(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        # Journal bank con outstanding accounts seteados (igual que los otros tests)
        cls.pay_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        outstanding_account = cls.env["account.account"].search(
            [("company_ids", "=", cls.company.id), ("account_type", "=", "asset_current")], limit=1
        )
        if outstanding_account:
            for pml in cls.pay_journal.inbound_payment_method_line_ids:
                if not pml.payment_account_id:
                    pml.payment_account_id = outstanding_account
            for pml in cls.pay_journal.outbound_payment_method_line_ids:
                if not pml.payment_account_id:
                    pml.payment_account_id = outstanding_account

        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )

        ar = cls.env.ref("base.ar", raise_if_not_found=False)
        partner_vals = {"name": "Pay Now Partner"}
        if ar:
            partner_vals["country_id"] = ar.id
        cls.partner = cls.env["res.partner"].create(partner_vals)
        cls.product = cls.env.ref("product.product_product_16")

    def _make_invoice(self, move_type, journal):
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner.id,
                "invoice_date": self.today,
                "move_type": move_type,
                "journal_id": journal.id,
                "company_id": self.company.id,
                "pay_now_journal_id": self.pay_journal.id,
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
