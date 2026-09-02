from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestResetCycle(AccountInvariantsMixin, TransactionCase):
    """Ciclo de restablecer a borrador de un pago confirmado y conciliado.

    FCP-R09: volver a borrador un pago daba error, o volvía dejando el estado
    inconsistente (la factura seguía pagada, el asiento seguía conciliado), o al
    re-confirmar no volvía a conciliar y habilitaba pagos duplicados. D2: la
    operación desconcilia y se edita el mismo pago — no revierte ni genera uno
    nuevo.

    Cubre FCP-R09-E1/E7/E8/E9.
    Tickets 120230, 120501, 121622, 121844, 122207.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )
        # Configuración del escenario, para que el estado de pago sea inequívoco:
        # un diario que asienta directo en la cuenta de banco, sin transitoria. Así
        # la factura queda "pagada" al confirmar y no "en proceso de pago", que es
        # otro escenario (FCP-R06) y no lo que se mide acá.
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "Test Reset Cycle Bank", "type": "bank", "code": "TRCB", "company_id": cls.company.id}
        )
        cls.bank_journal.outbound_payment_method_line_ids.payment_account_id = cls.bank_journal.default_account_id
        cls.product = cls.env.ref("product.product_product_16")
        cls.vendor = cls.env["res.partner"].create({"name": "Test Reset Cycle Vendor"})
        write_off_account = cls.env["account.account"].search([("account_type", "=", "expense")], limit=1)
        cls.write_off_type = cls.env["account.write_off.type"].create(
            {"name": "Test Reset Cycle Write-off Type", "account_id": write_off_account.id}
        )

    def _make_bill(self, amount):
        bill = self.env["account.move"].create(
            {
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-01",
                "move_type": "in_invoice",
                "journal_id": self.purchase_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1, "price_unit": amount})
                ],
            }
        )
        bill.action_post()
        return bill

    def _debt_lines(self, bills):
        return bills.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")

    def _make_payment(self, debt_lines, amount, date="2026-01-01"):
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": date,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )
        payment.amount = amount
        return payment

    def test_reset_edits_the_same_payment_and_reconfirming_does_not_duplicate_it(self):
        """Dado un pago a proveedor de $50.000 confirmado y conciliado contra su
        factura, cuando se restablece a borrador, se cambia la fecha y se
        re-confirma, entonces se editó el mismo pago: el asiento es el mismo (no
        hay reversión), la factura pasó por no pagada y volvió a pagada contra
        ese único pago, y el dato editado se conservó.

        Cubre FCP-R09-E1.
        """
        bill = self._make_bill(50000.0)
        payment = self._make_payment(self._debt_lines(bill), 50000.0)
        payment.action_post()
        self.assert_payment_invariants(payment, "pago inicial")
        move_before = payment.move_id

        with self.subTest("confirmado y conciliado: la factura queda pagada"):
            self.assertEqual(bill.payment_state, "paid")
            self.assertEqual(bill.amount_residual, 0.0)
            self.assertEqual(bill.reconciled_payment_ids, payment)

        payment.action_draft()
        with self.subTest("vuelto a borrador sin error, sobre el mismo asiento"):
            self.assertEqual(payment.state, "draft")
            # D2: la operación desconcilia y edita; si acá apareciera un asiento
            # nuevo, el usuario terminaría con dos comprobantes por un solo pago.
            self.assertEqual(payment.move_id, move_before)
            self.assertFalse(move_before.reversal_move_ids, "no se generó asiento de reversión")
        with self.subTest("la deuda se reabre por el importe completo"):
            self.assertEqual(bill.payment_state, "not_paid")
            self.assertEqual(bill.amount_residual, 50000.0)

        payment.date = "2026-02-05"
        payment.action_post()
        self.assert_payment_invariants(payment, "pago re-confirmado")

        with self.subTest("re-confirmado: la factura queda pagada contra ese mismo pago"):
            self.assertEqual(bill.payment_state, "paid")
            self.assertEqual(bill.amount_residual, 0.0)
            self.assertEqual(bill.reconciled_payment_ids, payment)
        with self.subTest("no aparece un segundo apunte de banco ni saldo pendiente nuevo"):
            bank_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type in ("asset_cash", "liability_credit_card")
            )
            self.assertEqual(len(bank_lines), 1)
            self.assertEqual(bank_lines.balance, -50000.0)
        with self.subTest("el pago conserva el dato editado"):
            self.assertEqual(str(payment.date), "2026-02-05")

    def test_reset_of_a_payment_with_write_off_does_not_leave_the_adjustment_twice(self):
        """Dado un pago con write-off por la diferencia, cuando vuelve a borrador
        y se re-confirma, entonces la línea de ajuste sigue siendo una sola por
        el importe original — ni duplicada ni una segunda en cero.

        Cubre FCP-R09-E7.
        """
        bill = self._make_bill(50100.0)
        payment = self._make_payment(self._debt_lines(bill), 50000.0)
        payment.write_off_type_id = self.write_off_type
        payment.action_adjust_writeoff_for_difference()
        payment.action_post()
        self.assert_payment_invariants(payment, "pago con write-off inicial")

        payment.action_draft()
        with self.subTest("en borrador el ajuste sigue declarado, no se pierde"):
            self.assertEqual(payment.write_off_amount, 100.0)

        payment.action_post()
        self.assert_payment_invariants(payment, "pago con write-off re-confirmado")
        with self.subTest("una sola línea de ajuste, por el importe original"):
            write_off_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == self.write_off_type.account_id
            )
            self.assertEqual(len(write_off_lines), 1)
            self.assertEqual(write_off_lines.balance, -100.0)
        with self.subTest("ninguna línea quedó en cero"):
            self.assertFalse(
                payment.move_id.line_ids.filtered(lambda line: self.company.currency_id.is_zero(line.balance))
            )
        with self.subTest("la factura vuelve a quedar pagada"):
            self.assertEqual(bill.payment_state, "paid")

    def test_reset_of_a_payment_of_two_bills_reopens_both(self):
        """Dado un pago que cancela dos facturas ($30.000 + $20.000), cuando
        vuelve a borrador, entonces las dos vuelven a no pagada con su importe
        completo — ninguna queda saldada sin comprobante. Al re-confirmar, las
        dos vuelven a pagada contra el mismo pago.

        Cubre FCP-R09-E8 (AS7-014: con una sola factura no se detecta).
        """
        bill_a = self._make_bill(30000.0)
        bill_b = self._make_bill(20000.0)
        payment = self._make_payment(self._debt_lines(bill_a + bill_b), 50000.0)
        payment.action_post()
        self.assert_payment_invariants(payment, "pago de dos facturas")

        with self.subTest("confirmado: las dos facturas quedan pagadas"):
            self.assertEqual(bill_a.payment_state, "paid")
            self.assertEqual(bill_b.payment_state, "paid")

        payment.action_draft()
        with self.subTest("vuelto a borrador: ninguna de las dos queda saldada"):
            self.assertEqual(bill_a.payment_state, "not_paid")
            self.assertEqual(bill_b.payment_state, "not_paid")
            self.assertEqual(bill_a.amount_residual, 30000.0)
            self.assertEqual(bill_b.amount_residual, 20000.0)

        payment.action_post()
        self.assert_payment_invariants(payment, "pago de dos facturas re-confirmado")
        with self.subTest("re-confirmado: las dos vuelven a pagada contra el mismo pago"):
            self.assertEqual(bill_a.payment_state, "paid")
            self.assertEqual(bill_b.payment_state, "paid")
            self.assertEqual(bill_a.reconciled_payment_ids, payment)
            self.assertEqual(bill_b.reconciled_payment_ids, payment)

    def test_deleting_the_payment_reopens_the_debt_instead_of_leaving_it_settled(self):
        """Dado un pago confirmado de dos facturas, cuando en vez de re-confirmar
        se lo vuelve a borrador y se lo elimina, entonces las dos facturas vuelven
        a no pagada: no quedan saldadas contra un comprobante que ya no existe.

        Cubre FCP-R09-E9.
        """
        bill_a = self._make_bill(30000.0)
        bill_b = self._make_bill(20000.0)
        payment = self._make_payment(self._debt_lines(bill_a + bill_b), 50000.0)
        payment.action_post()
        self.assert_payment_invariants(payment, "pago antes de eliminarlo")
        payment.action_draft()
        payment.unlink()

        with self.subTest("las dos facturas vuelven a no pagada con su importe completo"):
            self.assertEqual(bill_a.payment_state, "not_paid")
            self.assertEqual(bill_b.payment_state, "not_paid")
            self.assertEqual(bill_a.amount_residual, 30000.0)
            self.assertEqual(bill_b.amount_residual, 20000.0)
        with self.subTest("no queda ninguna conciliación colgada del pago borrado"):
            self.assertFalse(bill_a.reconciled_payment_ids)
            self.assertFalse(bill_b.reconciled_payment_ids)
