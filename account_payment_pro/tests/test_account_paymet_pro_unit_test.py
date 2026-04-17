from datetime import timedelta

from odoo import Command, fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestAccountPaymentProUnitTest(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super(TestAccountPaymentProUnitTest, cls).setUpClass()
        cls.today = fields.Date.today()
        cls.ar = ar = cls.env.ref("base.ar")

        cls.company = cls.env.company
        cls.company_bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        # Configurar cuentas outstanding en el diario de banco para que al postear
        # se genere asiento contable (sin esto Odoo no crea journal entry)
        outstanding_account = cls.env["account.account"].search(
            [("company_ids", "=", cls.company.id), ("account_type", "=", "asset_current")], limit=1
        )
        if outstanding_account:
            for pml in cls.company_bank_journal.inbound_payment_method_line_ids:
                if not pml.payment_account_id:
                    pml.payment_account_id = outstanding_account
            for pml in cls.company_bank_journal.outbound_payment_method_line_ids:
                if not pml.payment_account_id:
                    pml.payment_account_id = outstanding_account
        cls.company_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.company.use_payment_pro = True
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
        cls.partner_ri = cls.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))

    def test_create_payment_with_a_date_rate_then_change_rate(self):
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today - timedelta(days=14),
                "move_type": "out_invoice",
                "journal_id": self.company_journal.id,
                "company_id": self.company.id,
                "currency_id": self.eur_currency.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 100,
                        }
                    ),
                ],
            }
        )
        invoice.action_post()

        vals = {
            "journal_id": self.company_bank_journal.id,
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
        # Create invoice
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "out_invoice",
                "journal_id": self.company_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 100,
                        }
                    ),
                ],
            }
        )
        invoice.action_post()

        # Create and post payment
        vals = {
            "journal_id": self.company_bank_journal.id,
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
        # TODO improve. for this to work, saas_client_adhoc is needed to be installed (For setup of journal)
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
        purchase_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "purchase")], limit=1
        )
        # Crear nota de crédito de proveedor (in_refund genera débito en AP → amount_residual > 0)
        credit_note = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "in_refund",
                "journal_id": purchase_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 500,
                        }
                    ),
                ],
            }
        )
        credit_note.action_post()

        # payment_type=inbound con partner_type=supplier (caso invertido)
        debt_lines = credit_note.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.company_bank_journal.id,
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
        # Crear nota de crédito de cliente (genera crédito en AR → amount_residual < 0)
        credit_note = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "out_refund",
                "journal_id": self.company_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 300,
                        }
                    ),
                ],
            }
        )
        credit_note.action_post()

        # payment_type=outbound con partner_type=customer (caso invertido)
        debt_lines = credit_note.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.company_bank_journal.id,
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
        purchase_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "purchase")], limit=1
        )
        # Nota de crédito de proveedor (in_refund genera débito en AP → amount_residual > 0)
        credit_note = self.env["account.move"].create(
            {
                "partner_id": self.partner_ri.id,
                "invoice_date": self.today,
                "move_type": "in_refund",
                "journal_id": purchase_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": 1000,
                        }
                    ),
                ],
            }
        )
        credit_note.action_post()

        debt_lines = credit_note.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.company_bank_journal.id,
                "partner_id": self.partner_ri.id,
                "partner_type": "supplier",
                "payment_type": "inbound",
                "date": self.today,
                "amount": credit_note.amount_total,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )
        payment.action_post()

<<<<<<< f59c1442a8019e1f9554649bee69f71f259888b9
        self.assertIn(payment.state, ["paid", "in_process"], "El pago invertido debe poder postearse")
        self.assertIn(credit_note.payment_state, ["paid", "in_payment"], "La nota de crédito debe quedar pagada")
||||||| 0485f844ec6636a5174f05964afe4b03e8a9547e
        # Get liquidity lines
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )

        # Verify liquidity line balance uses forced amount
        liquidity_balance = sum(liquidity_lines.mapped("balance"))
        self.assertAlmostEqual(
            liquidity_balance,
            forced_amount,
            places=2,
            msg=f"Liquidity line balance should be {forced_amount} (forced), not {expected_normal_conversion} (normal conversion)",
        )

        # Verify amount_company_currency_signed_pro also uses forced amount
        self.assertEqual(
            payment.amount_company_currency_signed_pro,
            forced_amount,
            "amount_company_currency_signed_pro should use forced amount",
        )

        # Test that changes still preserve forced amount (synchronization)
        payment.action_draft()
        payment.memo = "Test synchronization"
        payment.action_post()

        # Verify liquidity lines still use forced amount after synchronization
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )
        liquidity_balance = sum(liquidity_lines.mapped("balance"))
        self.assertAlmostEqual(
            liquidity_balance,
            forced_amount,
            places=2,
            msg="Liquidity line balance should still use forced amount after synchronization",
        )
=======
        # Get liquidity lines
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )

        # Verify liquidity line balance uses forced amount
        liquidity_balance = sum(liquidity_lines.mapped("balance"))
        self.assertAlmostEqual(
            liquidity_balance,
            forced_amount,
            places=2,
            msg=f"Liquidity line balance should be {forced_amount} (forced), not {expected_normal_conversion} (normal conversion)",
        )

        # Verify amount_company_currency_signed_pro also uses forced amount
        self.assertEqual(
            payment.amount_company_currency_signed_pro,
            forced_amount,
            "amount_company_currency_signed_pro should use forced amount",
        )

        # Test that changes still preserve forced amount (synchronization)
        payment.action_draft()
        payment.memo = "Test synchronization"
        payment.action_post()

        # Verify liquidity lines still use forced amount after synchronization
        liquidity_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )
        liquidity_balance = sum(liquidity_lines.mapped("balance"))
        self.assertAlmostEqual(
            liquidity_balance,
            forced_amount,
            places=2,
            msg="Liquidity line balance should still use forced amount after synchronization",
        )

    def test_write_off_line_amounts_company_vs_payment_currency(self):
        """Minimal test: company currency vs payment currency, force company amount and check write-off line balance"""
        # Use existing company and ensure we have a different currency for the payment
        company_currency = self.company.currency_id

        # Use USD as payment currency (different from company currency)
        usd = self.env["res.currency"].with_context(active_test=False).search([("name", "=", "USD")], limit=1)
        usd.active = True

        # If company already uses USD, skip test since we need different currencies
        if company_currency == usd:
            self.skipTest("Test requires payment currency different from company currency")

        # create payment in USD but force company amount so exchange_rate = 1300
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_ri.id,
                "journal_id": self.company_bank_journal.id,
                "company_id": self.company.id,
                "amount": 1.0,
                "currency_id": usd.id,
                "force_amount_company_currency": 1300.0,
            }
        )

        # Create a dedicated account for write-off to avoid conflicts with payment accounts
        write_off_account = self.env["account.account"].create(
            {
                "name": "Write-Off Test Account",
                "code": "WOTEST001",
                "account_type": "expense",
                "company_id": self.company.id,
            }
        )
        wot = self.env["account.write_off.type"].create(
            {
                "name": "WOT Test",
                "label": "WOT Test",
                "company_ids": [(6, 0, [self.company.id])],
                "account_id": write_off_account.id,
            }
        )

        payment.write_off_type_id = wot
        payment.write_off_amount = 1000.0

        payment.action_post()

        write_off_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id == wot.account_id)
        self.assertTrue(write_off_lines, "No write-off move line found")
        self.assertEqual(len(write_off_lines), 1, "Expected exactly one write-off move line")

        line = write_off_lines[0]
        expected_amount_currency = 1000.0 / 1300.0
        expected_balance = 1000.0

        self.assertAlmostEqual(
            float(line.amount_currency or 0.0),
            expected_amount_currency,
            places=6,
            msg="amount_currency on write-off line is incorrect",
        )
        self.assertAlmostEqual(
            float(line.balance),
            expected_balance,
            places=2,
            msg="balance on write-off line should be the write_off_amount in company currency",
        )
>>>>>>> 14fd0e7c604fb37f189c6a4c36ae790a691743e1
