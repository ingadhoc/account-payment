from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestWriteOffAndRounding(AccountInvariantsMixin, TransactionCase):
    """Write-off real, saldo abierto por redondeo, y combinaciones de documentos.

    FCP-R04: en un pago por el importe exacto de la deuda, el sistema generaba igual
    una línea de ajuste ("balance automático") por $0 o por centavos, o dejaba la
    factura con saldo residual. D9: no hay tolerancia ni ajuste automático — si el
    total genera un redondeo, el usuario lo ajusta con un write-off; si no lo hace,
    queda saldo abierto. D5: la cuenta del ajuste la elige el usuario en el write-off,
    no sale de la config de compañía.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        cls.product = cls.env.ref("product.product_product_16")
        cls.vendor = cls.env["res.partner"].create({"name": "Test Write-off Vendor"})
        write_off_account = cls.env["account.account"].search([("account_type", "=", "expense")], limit=1)
        cls.write_off_type = cls.env["account.write_off.type"].create(
            {"name": "Test Write-off Type", "account_id": write_off_account.id}
        )

    def _make_bill(self, amount, move_type="in_invoice"):
        bill = self.env["account.move"].create(
            {
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-01",
                "move_type": move_type,
                "journal_id": self.purchase_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1, "price_unit": amount})
                ],
            }
        )
        bill.action_post()
        return bill

    def _make_payment(self, debt_lines, amount):
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": "2026-01-01",
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )
        payment.amount = amount
        return payment

    def test_real_write_off_lands_in_the_account_the_user_chose_and_survives_a_reset(self):
        """Diferencia real de $100 declarada como ajuste: existe la línea por $100
        exactos, en la cuenta que el usuario eligió en el write-off (D5, no la de
        config de compañía), y la factura queda pagada. Vuelto a borrador y
        re-confirmado sin cambios, la línea no se duplica ni queda una en cero.

        Cubre FCP-R04-E3/E9.
        """
        bill = self._make_bill(50100.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self._make_payment(debt, 50000.0)
        payment.write_off_type_id = self.write_off_type
        payment.action_adjust_writeoff_for_difference()

        with self.subTest("el ajuste es exactamente la diferencia, sin redondeos raros"):
            self.assertEqual(payment.write_off_amount, 100.0)
            self.assertEqual(payment.payment_difference, 0.0)

        payment.action_post()
        self.assert_payment_invariants(payment, "pago con write-off real")
        with self.subTest("la línea de ajuste está en la cuenta que eligió el usuario"):
            write_off_line = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == self.write_off_type.account_id
            )
            self.assertEqual(len(write_off_line), 1)
            self.assertEqual(write_off_line.balance, -100.0)
        with self.subTest("la factura queda pagada"):
            self.assertEqual(bill.amount_residual, 0.0)

        payment.action_draft()
        payment.action_post()
        self.assert_payment_invariants(payment, "pago con write-off tras reset")
        with self.subTest("tras el reset, sigue una sola línea de ajuste, no duplicada ni en cero"):
            write_off_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == self.write_off_type.account_id
            )
            self.assertEqual(len(write_off_lines), 1)
            self.assertEqual(write_off_lines.balance, -100.0)

    def test_real_difference_left_open_stays_partial_without_an_adjustment_line(self):
        """Diferencia real de $100, dejada sin cargar como ajuste: la factura queda
        en pago parcial con saldo $100 — sin línea de write-off, a diferencia del
        caso donde el usuario sí la carga (arriba).

        Cubre FCP-R04-E4.
        """
        bill = self._make_bill(50100.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self._make_payment(debt, 50000.0)
        self.assertEqual(payment.payment_difference, 100.0)

        payment.action_post()
        self.assert_payment_invariants(payment, "diferencia real sin ajuste")
        with self.subTest("la factura queda en pago parcial con el saldo abierto"):
            self.assertEqual(bill.payment_state, "partial")
            self.assertEqual(bill.amount_residual, 100.0)
        with self.subTest("sin línea de ajuste: nadie cargó un write-off"):
            self.assertFalse(
                payment.move_id.line_ids.filtered(lambda line: line.account_id == self.write_off_type.account_id)
            )

    def test_rounding_without_write_off_leaves_an_open_balance_never_a_zero_line(self):
        """Deuda de $100,01 pagada con $100,00: sin write-off cargado, la factura
        queda en pago parcial con saldo $0,01 — no hay tolerancia ni ajuste
        automático (D9). Con write-off de $0,01 cargado, la factura queda pagada y
        aparece una línea de ajuste de $0,01 — nunca una de $0,00.

        Cubre FCP-R04-E6.
        """
        with self.subTest("sin write-off: queda pago parcial con el centavo abierto"):
            bill = self._make_bill(100.01)
            debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
            payment = self._make_payment(debt, 100.0)
            self.assertEqual(payment.payment_difference, 0.01)
            payment.action_post()
            self.assert_payment_invariants(payment, "redondeo sin write-off")
            self.assertEqual(bill.payment_state, "partial")
            self.assertEqual(bill.amount_residual, 0.01)
            self.assertFalse(
                payment.move_id.line_ids.filtered(lambda line: self.company.currency_id.is_zero(line.balance)),
                "nunca una línea de importe $0",
            )

        with self.subTest("con write-off de un centavo: factura pagada, una línea de $0,01"):
            bill_wo = self._make_bill(100.01)
            debt_wo = bill_wo.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
            payment_wo = self._make_payment(debt_wo, 100.0)
            payment_wo.write_off_type_id = self.write_off_type
            payment_wo.action_adjust_writeoff_for_difference()
            payment_wo.action_post()
            self.assert_payment_invariants(payment_wo, "redondeo con write-off de un centavo")
            self.assertEqual(bill_wo.amount_residual, 0.0)
            write_off_line = payment_wo.move_id.line_ids.filtered(
                lambda line: line.account_id == self.write_off_type.account_id
            )
            self.assertEqual(write_off_line.balance, -0.01)

    def test_two_invoices_paid_exact_produce_one_bank_line_without_adjustment(self):
        """Pago exacto de dos facturas ($60.000 + $40.000): cada una queda pagada,
        una sola línea de banco por $100.000, sin ajuste.

        Cubre FCP-R04-E7.
        """
        bill_1 = self._make_bill(60000.0)
        bill_2 = self._make_bill(40000.0)
        debt = (bill_1 | bill_2).line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self._make_payment(debt, 100000.0)

        self.assertEqual(payment.payment_difference, 0.0)
        payment.action_post()
        self.assert_payment_invariants(payment, "pago exacto de dos facturas")

        self.assertEqual(bill_1.amount_residual, 0.0)
        self.assertEqual(bill_2.amount_residual, 0.0)
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )
        self.assertEqual(len(liquidity_lines), 1)
        self.assertEqual(liquidity_lines.balance, -100000.0)
        self.assertFalse(
            payment.move_id.line_ids.filtered(lambda line: line.account_id == self.write_off_type.account_id)
        )

    def test_credit_note_combination_does_not_inflate_the_difference(self):
        """Factura $110.000 − NC $10.000, pago $100.000: saldo 0 en ambos
        documentos, sin ajuste — los signos no inflan la diferencia.

        Cubre FCP-R04-E8.
        """
        bill = self._make_bill(110000.0)
        credit_note = self._make_bill(10000.0, move_type="in_refund")
        debt = (bill | credit_note).line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self._make_payment(debt, 100000.0)

        self.assertEqual(payment.to_pay_amount, 100000.0, "la NC ya resta en el total a pagar")
        self.assertEqual(payment.payment_difference, 0.0)

        payment.action_post()
        self.assert_payment_invariants(payment, "pago con factura y NC combinadas")
        self.assertEqual(bill.amount_residual, 0.0)
        self.assertEqual(credit_note.amount_residual, 0.0)
        self.assertFalse(
            payment.move_id.line_ids.filtered(lambda line: line.account_id == self.write_off_type.account_id)
        )


@tagged("post_install", "-at_install")
class TestWriteOffMulticurrency(AccountInvariantsMixin, TransactionCase):
    """Write-off + diferencia de cambio en la misma operación: dos mecanismos que
    se confunden a mano (D3, D5). Usa como "moneda extranjera" una distinta de
    la de la compañía activa (``env.company``), sea cual sea esa compañía.
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

        cls.vendor = cls.env["res.partner"].create({"name": "Test Write-off Multicurrency Vendor"})
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        write_off_account = cls.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "=", cls.company.id)], limit=1
        )
        cls.write_off_type = cls.env["account.write_off.type"].create(
            {"name": "Test Write-off Multicurrency Type", "account_id": write_off_account.id}
        )

    def test_write_off_and_exchange_difference_are_two_separate_lines(self):
        """Factura USD 1.000 (TC 1.000) pagada con USD 999 al TC 1.100: el ajuste
        es por USD 1 al TC del pago (1.100, o sea $1.100) — separado de la
        diferencia de cambio de los USD 999 ya devengados ($100.000). Dos líneas
        en dos asientos distintos, no una sola que las mezcle.

        Cubre FCP-R04-E5.
        """
        expense = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "=", self.company.id)], limit=1
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-01",
                "company_id": self.company.id,
                "currency_id": self.usd.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test write-off multicurrency line",
                            "quantity": 1,
                            "price_unit": 1000.0,
                            "account_id": expense.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        bill.action_post()
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
        payment.amount = 999.0
        payment.write_off_type_id = self.write_off_type
        payment.action_adjust_writeoff_for_difference()
        payment.action_post()
        self.assert_payment_invariants(payment, "pago con write-off y diferencia de cambio")

        with self.subTest("el write-off es 1 USD al TC del pago, en su propia línea"):
            write_off_line = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == self.write_off_type.account_id
            )
            self.assertEqual(write_off_line.amount_currency, -1.0)
            self.assertEqual(write_off_line.balance, -1100.0)

        with self.subTest("la diferencia de cambio es un asiento separado, no mezclado con el write-off"):
            self.assertTrue(payment.exchange_diff_move_ids)
            self.assertNotIn(payment.move_id, payment.exchange_diff_move_ids)
            exchange_lines = payment.exchange_diff_move_ids.line_ids.filtered(
                lambda line: line.account_id.account_type == "liability_payable"
            )
            self.assertEqual(self.company.currency_id.round(sum(exchange_lines.mapped("balance"))), -100000.0)

        with self.subTest("la factura queda saldada"):
            self.assertEqual(bill.amount_residual, 0.0)
