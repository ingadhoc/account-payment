from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPartnerLedgerSign(TransactionCase):
    """El signo del mayor del partner al cobrar/pagar con el pago múltiple.

    FCP-R03: se registraba un cobro de cliente y la deuda AUMENTABA en vez de bajar
    — el movimiento entraba con el signo invertido en la cuenta corriente. Es el
    espejo de FCP-R02 (mismo motor de ``to_pay_move_line_ids``/``payment_total``),
    así que no se duplica el escenario base: se parametriza cliente/proveedor.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        cls.product = cls.env.ref("product.product_product_16")
        cls.customer = cls.env["res.partner"].create({"name": "Test Ledger Sign Customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Test Ledger Sign Vendor"})

    def _make_invoice(self, partner, amount, move_type):
        journal = self.sale_journal if move_type in ("out_invoice", "out_refund") else self.purchase_journal
        invoice = self.env["account.move"].create(
            {
                "partner_id": partner.id,
                "invoice_date": "2026-01-01",
                "move_type": move_type,
                "journal_id": journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1, "price_unit": amount})
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _make_payment(self, partner, partner_type, payment_type, debt_lines, amount=None):
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": partner.id,
                "partner_type": partner_type,
                "payment_type": payment_type,
                "date": "2026-01-01",
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)] if debt_lines else [Command.clear()],
            }
        )
        if amount is not None:
            payment.amount = amount
        return payment

    def test_customer_receipt_and_vendor_payment_net_the_debt_with_the_right_sign(self):
        """Base parametrizada (FCP-R03-E1/E2): factura de $30.000 y su pago —
        cobro de cliente o pago a proveedor — netean la deuda a cero con el signo
        correcto, sin invertirlo.
        """
        with self.subTest("cliente: el cobro resta la deuda, no la suma"):
            invoice = self._make_invoice(self.customer, 30000.0, "out_invoice")
            debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
            self.assertEqual(debt.amount_residual, 30000.0, "saldo a cobrar antes del pago")
            payment = self._make_payment(self.customer, "customer", "inbound", debt, amount=30000.0)
            payment.action_post()
            self.assertEqual(invoice.amount_residual, 0.0)
            self.assertEqual(invoice.payment_state, "in_payment", "paid recién al conciliar la cuenta pendiente")
            liquidity = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.outstanding_account_id
            )
            self.assertEqual(liquidity.balance, 30000.0, "el banco entra al debe")
            self.assertEqual(
                debt.balance, 30000.0, "la factura del cliente sigue al debe: la conciliación no le cambia el signo"
            )

        with self.subTest("proveedor: el pago resta la deuda, no la suma"):
            bill = self._make_invoice(self.vendor, 30000.0, "in_invoice")
            debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
            self.assertEqual(debt.amount_residual, -30000.0, "saldo a pagar antes del pago")
            payment = self._make_payment(self.vendor, "supplier", "outbound", debt, amount=30000.0)
            payment.action_post()
            self.assertEqual(bill.amount_residual, 0.0)
            self.assertEqual(bill.payment_state, "in_payment", "paid recién al conciliar la cuenta pendiente")
            liquidity = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.outstanding_account_id
            )
            self.assertEqual(liquidity.balance, -30000.0, "el banco sale al haber")
            self.assertEqual(debt.balance, -30000.0, "la factura del proveedor sigue al haber")

    def test_credit_note_subtracts_instead_of_adding(self):
        """Cliente con NC de $10.000 y factura de $30.000: un cobro de $20.000
        imputando ambas deja todo en cero — la NC resta, no suma.

        Cubre FCP-R03-E3.
        """
        invoice = self._make_invoice(self.customer, 30000.0, "out_invoice")
        credit_note = self._make_invoice(self.customer, 10000.0, "out_refund")
        debt = (invoice | credit_note).line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

        payment = self._make_payment(self.customer, "customer", "inbound", debt, amount=20000.0)
        self.assertEqual(payment.to_pay_amount, 20000.0, "la NC ya resta en el total a cobrar")
        payment.action_post()

        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(credit_note.amount_residual, 0.0)

    def test_previous_credit_balance_is_applied_without_flipping_signs(self):
        """Cliente con saldo a favor previo de $5.000 (un cobro a cuenta ya
        confirmado) y una factura nueva de $30.000: cobrar $25.000 imputando
        ambos dos dejan todo en cero, aplicando el crédito previo.

        Cubre FCP-R03-E4.
        """
        customer = self.env["res.partner"].create({"name": "Test Ledger Sign Customer E4"})
        advance = self._make_payment(customer, "customer", "inbound", debt_lines=None, amount=5000.0)
        advance.action_post()
        advance_line = advance.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        self.assertEqual(advance_line.amount_residual, -5000.0, "el saldo a favor previo")

        invoice = self._make_invoice(customer, 30000.0, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")

        payment = self._make_payment(customer, "customer", "inbound", debt | advance_line, amount=25000.0)
        payment.action_post()

        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(advance_line.amount_residual, 0.0, "el saldo a favor previo quedó aplicado, no duplicado")

    def test_receipt_imputing_an_invoice_and_a_previous_payment_on_account_has_no_spurious_lines(self):
        """Cobro que imputa, en la MISMA operación, una factura nueva y un pago a
        cuenta previo del mismo cliente: netean correctamente y el asiento del
        cobro no arrastra líneas espurias de la OP previa.

        Cubre FCP-R03-E5 (BUG-004): solo se ve con un pago previo real del mismo
        partner en danza — a mano nadie arma ese estado previo para probarlo.
        """
        customer = self.env["res.partner"].create({"name": "Test Ledger Sign Customer E5"})
        previous_payment = self._make_payment(customer, "customer", "inbound", debt_lines=None, amount=10000.0)
        previous_payment.action_post()
        previous_line = previous_payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

        invoice = self._make_invoice(customer, 30000.0, "out_invoice")
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")

        payment = self._make_payment(customer, "customer", "inbound", debt | previous_line, amount=20000.0)
        payment.action_post()

        with self.subTest("la factura queda saldada"):
            self.assertEqual(invoice.amount_residual, 0.0)
        with self.subTest("el asiento del cobro no arrastra líneas espurias de la OP previa"):
            self.assertEqual(len(payment.move_id.line_ids), 2)
            liquidity = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.outstanding_account_id
            )
            self.assertEqual(liquidity.balance, 20000.0)
