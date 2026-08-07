from datetime import timedelta

from odoo import Command
from odoo.tests import tagged

from .common import PaymentProCommon


@tagged("post_install", "-at_install")
class TestAccountPaymentProUnitTest(PaymentProCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Tasas históricas de EUR: escenario propio de esta suite (congelamiento
        # de accounting_rate), no de la Common
        cls.eur_currency = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "EUR")])
        cls.eur_currency.active = True
        cls.rates = cls.env["res.currency.rate"].create(
            [
                {
                    "name": "2024-01-01",
                    "inverse_company_rate": 800,
                    "currency_id": cls.eur_currency.id,
                    "company_id": cls.company.id,
                },
                {
                    "name": (cls.today - timedelta(days=10)).strftime("%Y-%m-%d"),
                    "inverse_company_rate": 1000,
                    "currency_id": cls.eur_currency.id,
                    "company_id": cls.company.id,
                },
            ]
        )

    def test_create_payment_with_a_date_rate_then_change_rate(self):
        invoice = self._create_invoice(currency=self.eur_currency, date=self.today - timedelta(days=14))

        vals = {
            "journal_id": self.bank_journal.id,
            "amount": invoice.amount_total,
            "currency_id": self.eur_currency.id,
            "date": self.today - timedelta(days=1),
        }
        action_context = invoice.action_register_payment()["context"]
        payment = self.env["account.payment"].with_context(**action_context).create(vals)
        payment.action_post()
        # accounting_rate = _get_conversion_rate(from=company_currency=ARS, to=EUR)
        # formato Odoo nativo: ej. 0.001 para "1 EUR = 1000 ARS"
        # El pago tiene date=today-1, por lo que aplica la tasa de today-10 (inverse_company_rate=1000)
        expected_rate_1 = self.env["res.currency"]._get_conversion_rate(
            from_currency=self.company.currency_id,
            to_currency=self.eur_currency,
            company=self.company,
            date=payment.date,
        )
        self.assertEqual(payment.accounting_rate, expected_rate_1, "no se tomo de forma correcta el tipo de cambio")
        self.rates[1].inverse_company_rate = 2000
        expected_rate_2 = self.env["res.currency"]._get_conversion_rate(
            from_currency=self.company.currency_id,
            to_currency=self.eur_currency,
            company=self.company,
            date=payment.date,
        )
        self.assertNotEqual(
            payment.accounting_rate,
            expected_rate_2,
            "Se tomo de forma incorrecta el tipo de cambio en un pago ya posteado",
        )
        self.assertEqual(payment.accounting_rate, expected_rate_1, "no se tomo de forma correcta el tipo de cambio")

        payment.action_draft()
        payment.date = self.today
        payment._compute_accounting_rate()
        payment.action_post()
        expected_rate_today = self.env["res.currency"]._get_conversion_rate(
            from_currency=self.company.currency_id,
            to_currency=self.eur_currency,
            company=self.company,
            date=self.today,
        )
        self.assertEqual(payment.accounting_rate, expected_rate_today, "no se tomo de forma correcta el tipo de cambio")

    def test_action_draft_unreconciles_payment(self):
        """Test that action_draft removes partial reconciliations when going back to draft"""
        invoice = self._create_invoice()

        # Create and post payment
        vals = {
            "journal_id": self.bank_journal.id,
            "amount": invoice.amount_total,
            "date": self.today,
        }
        action_context = invoice.action_register_payment()["context"]
        payment = self.env["account.payment"].with_context(**action_context).create(vals)
        payment.action_post()

        # Get payment lines and verify there are partial reconciliations
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in payment._get_valid_payment_account_types()
        )
        partials_before = payment_lines.mapped("matched_debit_ids") | payment_lines.mapped("matched_credit_ids")

        # Verify that partial reconciliations exist
        self.assertTrue(partials_before, "There should be partial reconciliations after posting the payment")
        self.assertTrue(payment.move_id.posted_before, "posted_before should be True after posting")

        # Store the payment_total before going to draft (to verify it's not reset to 0)
        payment_total_before = payment.payment_total

        # Call action_draft
        payment.action_draft()

        # Verify that posted_before is False
        self.assertFalse(payment.move_id.posted_before, "posted_before should be False after action_draft")

        # Verify that payment_total is preserved after action_draft (regression check)
        self.assertEqual(
            payment.payment_total,
            payment_total_before,
            f"payment_total should remain {payment_total_before} after action_draft, not reset to 0",
        )

        # Verify that partial reconciliations were removed
        payment_lines_after = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in payment._get_valid_payment_account_types()
        )
        partials_after = payment_lines_after.mapped("matched_debit_ids") | payment_lines_after.mapped(
            "matched_credit_ids"
        )
        self.assertFalse(partials_after, "Partial reconciliations should be removed after action_draft")

        # Verify payment is in draft state
        self.assertEqual(payment.state, "draft", "Payment should be in draft state after action_draft")

    # ==================================================================
    # Tests para payment_type invertido (outbound+customer, inbound+supplier)
    # ==================================================================

    def test_inbound_supplier_selected_debt_positive(self):
        """Pago de tipo inbound + supplier (nota de crédito de proveedor / reembolso).
        selected_debt, to_pay_amount y payment_difference deben calcularse
        correctamente con valores positivos."""
        # Nota de crédito de proveedor (in_refund genera débito en AP → amount_residual > 0)
        credit_note = self._create_invoice(move_type="in_refund", amount=500)

        # payment_type=inbound con partner_type=supplier (caso invertido)
        debt_lines = self._get_debt_lines(credit_note, "liability_payable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.partner_ri.id,
                "partner_type": "supplier",
                "payment_type": "inbound",
                "date": self.today,
                "amount": credit_note.amount_total,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )

        # selected_debt debe ser positivo (amount_residual > 0 * sign(inbound)=+1)
        self.assertGreater(payment.selected_debt, 0, "selected_debt debe ser positivo para inbound+supplier")
        self.assertGreater(payment.to_pay_amount, 0, "to_pay_amount debe ser positivo para inbound+supplier")
        self.assertAlmostEqual(
            payment.payment_total,
            payment.to_pay_amount,
            places=2,
            msg="payment_total debe cubrir to_pay_amount",
        )
        self.assertAlmostEqual(
            payment.payment_difference,
            0,
            places=2,
            msg="payment_difference debe ser ≈ 0 cuando amount cubre la deuda",
        )

    def test_outbound_customer_selected_debt_positive(self):
        """Pago de tipo outbound + customer (nota de crédito a cliente / reembolso).
        selected_debt, to_pay_amount y payment_difference deben calcularse
        correctamente con valores positivos."""
        # Nota de crédito de cliente (genera crédito en AR → amount_residual < 0)
        credit_note = self._create_invoice(move_type="out_refund", amount=300)

        # payment_type=outbound con partner_type=customer (caso invertido)
        debt_lines = self._get_debt_lines(credit_note, "asset_receivable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.partner_ri.id,
                "partner_type": "customer",
                "payment_type": "outbound",
                "date": self.today,
                "amount": credit_note.amount_total,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )

        # selected_debt debe ser positivo (amount_residual < 0 * sign(outbound)=-1 = positivo)
        self.assertGreater(payment.selected_debt, 0, "selected_debt debe ser positivo para outbound+customer")
        self.assertGreater(payment.to_pay_amount, 0, "to_pay_amount debe ser positivo para outbound+customer")
        self.assertAlmostEqual(
            payment.payment_total,
            payment.to_pay_amount,
            places=2,
            msg="payment_total debe cubrir to_pay_amount",
        )
        self.assertAlmostEqual(
            payment.payment_difference,
            0,
            places=2,
            msg="payment_difference debe ser ≈ 0 cuando amount cubre la deuda",
        )

    def test_reversed_payment_type_post(self):
        """Verificar que pagos con payment_type invertido se pueden postear
        y concilian la deuda correctamente."""
        # Nota de crédito de proveedor (in_refund genera débito en AP → amount_residual > 0)
        credit_note = self._create_invoice(move_type="in_refund", amount=1000)

        debt_lines = self._get_debt_lines(credit_note, "liability_payable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.partner_ri.id,
                "partner_type": "supplier",
                "payment_type": "inbound",
                "date": self.today,
                "amount": credit_note.amount_total,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )
        payment.action_post()

        self.assertIn(payment.state, ["paid", "in_process"], "El pago invertido debe poder postearse")
        self.assertIn(credit_note.payment_state, ["paid", "in_payment"], "La nota de crédito debe quedar pagada")
