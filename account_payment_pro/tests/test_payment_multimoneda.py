"""
Tests para el modelo tri-monetario de account_payment_pro
=========================================================

Validan los 10 casos de uso de spec.md y la mecánica interna del modelo
de tres monedas (A / B1 / B2 / C).

Convención de monedas (spec.md §Modelo de monedas):
    A  = currency_id              — moneda del diario (liquidez)
    B1 = counterpart_currency_id  — moneda del apunte AP/AR (stored)
    B2 = destination_currency_id  — moneda de UX/conciliación (non-stored)
    C  = company_currency_id      — moneda contable (ARS)

    Sin reconcile_on_company_currency → B1 = B2.
    Con reconcile_on_company_currency → B1 puede diferir de B2.

Convención de rates (formato Odoo nativo):
    accounting_rate  = _get_conversion_rate(C, A)  →  amount_A = amount_C × rate
    counterpart_rate = _get_conversion_rate(A, B1)  →  amount_B1 = amount_A × rate

Rates de referencia para todos los tests:
    1 USD = 1 200 ARS  →  accounting_rate(C→USD) ≈ 0.000833
    1 EUR = 1 320 ARS  →  accounting_rate(C→EUR) ≈ 0.000758
    USD→EUR (transitividad) = 1320/1200 = 1.1
"""

from odoo import Command, fields
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPaymentMultimoneda(TestArCommon):
    """Tests del modelo tri-monetario (A / B1 / B2 / C)."""

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()

        cls.company = cls.company_ri
        cls.company.use_payment_pro = True

        # Monedas: C = ARS (company), A puede ser ARS/USD/EUR
        cls.ars = cls.company.currency_id
        cls.usd = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "USD")])
        cls.usd.active = True
        cls.eur = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "EUR")])
        cls.eur.active = True

        # Rates: 1 USD = 1200 ARS, 1 EUR = 1320 ARS
        cls.env["res.currency.rate"].create(
            [
                {
                    "name": cls.today,
                    "currency_id": cls.usd.id,
                    "company_id": cls.company.id,
                    "inverse_company_rate": 1200.0,
                },
                {
                    "name": cls.today,
                    "currency_id": cls.eur.id,
                    "company_id": cls.company.id,
                    "inverse_company_rate": 1320.0,
                },
            ]
        )

        # Diarios de banco (determinan moneda A)
        cls.bank_ars = cls._make_bank_journal("BARS", cls.ars)
        cls.bank_usd = cls._make_bank_journal("BUSD", cls.usd)
        cls.bank_eur = cls._make_bank_journal("BEUR", cls.eur)

        # Diarios de facturación (sin documentos fiscales, simplifica tests)
        cls.sale_journal = cls.env["account.journal"].create(
            {
                "name": "Ventas Test",
                "type": "sale",
                "code": "STEST",
                "company_id": cls.company.id,
                "l10n_latam_use_documents": False,
            }
        )
        cls.purchase_journal = cls.env["account.journal"].create(
            {
                "name": "Compras Test",
                "type": "purchase",
                "code": "PTEST",
                "company_id": cls.company.id,
                "l10n_latam_use_documents": False,
            }
        )

        cls.partner = cls.res_partner_adhoc
        cls.account_receivable = cls.company_data["default_account_receivable"]
        cls.account_payable = cls.company_data["default_account_payable"]
        cls.account_revenue = cls.company_data["default_account_revenue"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _make_bank_journal(cls, code, currency):
        return cls.env["account.journal"].create(
            {
                "name": f"Banco {currency.name}",
                "type": "bank",
                "code": code,
                "company_id": cls.company.id,
                "currency_id": currency.id,
            }
        )

    def _create_invoice(self, amount, currency, move_type="out_invoice"):
        """Crea y postea una factura cuyo *total con IVA 21 %* es ``amount``."""
        tax = self.tax_21_purchase if move_type == "in_invoice" else self.tax_21
        journal = self.purchase_journal if move_type == "in_invoice" else self.sale_journal
        price_unit = amount / (1 + tax.amount / 100.0)
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner.id,
                "invoice_date": self.today,
                "date": self.today,
                "move_type": move_type,
                "journal_id": journal.id,
                "currency_id": currency.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test",
                            "quantity": 1,
                            "price_unit": price_unit,
                            "account_id": self.account_revenue.id,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _create_payment(self, journal, partner_type="customer", payment_type="inbound", **kw):
        """Crea un pago en borrador."""
        vals = {
            "journal_id": journal.id,
            "partner_id": self.partner.id,
            "partner_type": partner_type,
            "payment_type": payment_type,
            "date": self.today,
        }
        vals.update(kw)
        return self.env["account.payment"].create(vals)

    def _get_debt_lines(self, invoice, account_type=None):
        """Devuelve las líneas de deuda (AR o AP) de una factura."""
        if account_type is None:
            account_type = (
                "asset_receivable" if invoice.move_type in ("out_invoice", "out_refund") else "liability_payable"
            )
        return invoice.line_ids.filtered(lambda l: l.account_id.account_type == account_type)

    def _get_rate(self, from_currency, to_currency):
        """Shortcut: rate Odoo nativo entre dos monedas a la fecha del test."""
        return self.env["res.currency"]._get_conversion_rate(
            from_currency=from_currency,
            to_currency=to_currency,
            company=self.company,
            date=self.today,
        )

    # -- Assertions compactas --

    def _assert_currencies(self, payment, *, A, B1, B2, C):
        """Verifica las 4 monedas del modelo tri-monetario en una sola llamada."""
        self.assertEqual(payment.currency_id, A, f"A (currency_id) esperado {A.name}")
        self.assertEqual(payment.counterpart_currency_id, B1, f"B1 (counterpart) esperado {B1.name}")
        self.assertEqual(payment.destination_currency_id, B2, f"B2 (destination) esperado {B2.name}")
        self.assertEqual(payment.company_currency_id, C, f"C (company) esperado {C.name}")

    def _assert_rates(self, payment, *, accounting=None, counterpart=None, places=6):
        """Verifica accounting_rate y/o counterpart_rate."""
        if accounting is not None:
            self.assertAlmostEqual(
                payment.accounting_rate,
                accounting,
                places=places,
                msg=f"accounting_rate: esperado {accounting}",
            )
        if counterpart is not None:
            self.assertAlmostEqual(
                payment.counterpart_rate,
                counterpart,
                places=places,
                msg=f"counterpart_rate: esperado {counterpart}",
            )

    def _assert_move_lines(self, payment, expected):
        """
        Verifica los apuntes contables del asiento de pago.

        ``expected`` es un dict con claves por rol de línea::

            {
                'liquidity':   {'currency': res.currency, 'amt_currency': float, 'balance': float},
                'counterpart': {'currency': res.currency, 'amt_currency': float, 'balance': float},
                'write_off':   {...},  # opcional
            }

        Verificaciones adicionales:
        - move_id.state == 'posted'
        - Partida doble: sum(balance) == 0
        """
        self.assertEqual(
            payment.move_id.state,
            "posted",
            f"El asiento debe estar posteado (payment.state={payment.state})",
        )
        lines = payment.move_id.line_ids

        # Partida doble
        total_balance = sum(lines.mapped("balance"))
        self.assertAlmostEqual(total_balance, 0, places=2, msg="Partida doble: sum(balance) debe ser 0")

        # Mapeo rol → account
        role_account = {
            "liquidity": payment.outstanding_account_id,
            "counterpart": payment.destination_account_id,
        }

        for role, exp in expected.items():
            if role == "write_off":
                account = payment.write_off_type_id.account_id
            else:
                account = role_account.get(role)
            self.assertTrue(account, f"No se pudo determinar la cuenta para rol '{role}'")
            matching = lines.filtered(lambda l, acc=account: l.account_id == acc)
            self.assertTrue(matching, f"No se encontró línea para {role} (cuenta {account.display_name})")
            line = matching[0]
            self.assertEqual(
                line.currency_id,
                exp["currency"],
                f"{role}: moneda esperada {exp['currency'].name}, obtenida {line.currency_id.name}",
            )
            self.assertAlmostEqual(
                line.amount_currency,
                exp["amt_currency"],
                places=2,
                msg=f"{role}: amount_currency",
            )
            self.assertAlmostEqual(
                line.balance,
                exp["balance"],
                places=2,
                msg=f"{role}: balance",
            )

    # ==================================================================
    # CASOS SIN reconcile_on_company_currency (B1 = B2)
    # ==================================================================

    def test_caso1_pago_local_simple(self):
        """Caso 1 · ARS → ARS → ARS
        Todas las monedas iguales, rates = 1.0. Verifica:
        - Monedas: A = B1 = B2 = C = ARS
        - counterpart_currency_amount = amount (sin conversión)
        - Asiento: liquidez +10 000, contrapartida −10 000 (todo ARS)
        - Factura queda pagada
        """
        invoice = self._create_invoice(10_000, self.ars)
        payment = self._create_payment(
            self.bank_ars,
            amount=10_000,
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice).ids)],
        )

        self._assert_currencies(payment, A=self.ars, B1=self.ars, B2=self.ars, C=self.ars)
        self._assert_rates(payment, accounting=1.0, counterpart=1.0)
        self.assertEqual(payment.counterpart_currency_amount, 10_000)

        payment.action_post()

        self._assert_move_lines(
            payment,
            {
                "liquidity": {"currency": self.ars, "amt_currency": 10_000, "balance": 10_000},
                "counterpart": {"currency": self.ars, "amt_currency": -10_000, "balance": -10_000},
            },
        )
        self.assertIn(invoice.payment_state, ["paid", "in_payment"])

    def test_caso2_pago_divisa_pura(self):
        """Caso 2 · USD → USD → ARS
        Pago y deuda en la misma divisa. Verifica:
        - Monedas: A = B1 = B2 = USD, C = ARS
        - accounting_rate = rate(C→A), counterpart_rate = 1.0
        - Asiento: liquidez +100 USD / +120 000 ARS, contrapartida inversa
        - to_pay_amount_company_currency ≈ 120 000 ARS
        """
        invoice = self._create_invoice(100, self.usd)
        payment = self._create_payment(
            self.bank_usd,
            amount=100,
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice).ids)],
        )

        expected_acc_rate = self._get_rate(self.ars, self.usd)  # ≈ 0.000833

        self._assert_currencies(payment, A=self.usd, B1=self.usd, B2=self.usd, C=self.ars)
        self._assert_rates(payment, accounting=expected_acc_rate, counterpart=1.0)
        self.assertEqual(payment.counterpart_currency_amount, 100)

        # to_pay_amount_company_currency = to_pay_amount / accounting_rate ≈ 120 000
        self.assertAlmostEqual(
            payment.to_pay_amount_company_currency,
            100 / expected_acc_rate,
            places=0,
        )

        payment.action_post()

        expected_balance = 100 / expected_acc_rate  # ≈ 120 000 ARS
        self._assert_move_lines(
            payment,
            {
                "liquidity": {"currency": self.usd, "amt_currency": 100, "balance": expected_balance},
                "counterpart": {"currency": self.usd, "amt_currency": -100, "balance": -expected_balance},
            },
        )
        self.assertIn(invoice.payment_state, ["paid", "in_payment"])

    def test_caso3_compra_de_divisa(self):
        """Caso 3 · ARS → USD → ARS  (compra de divisa)
        Pago en ARS para cancelar deuda en USD. Verifica:
        - Monedas: A = C = ARS, B1 = B2 = USD
        - accounting_rate = 1.0 (A = C)
        - counterpart_rate compute desde rate de mercado (usuario puede overridear)
        - counterpart_currency_amount = amount × counterpart_rate
        - Asiento: liquidez en ARS, contrapartida en USD con amount_currency
        """
        invoice = self._create_invoice(100, self.usd, move_type="in_invoice")
        debt_lines = self._get_debt_lines(invoice)
        payment = self._create_payment(
            self.bank_ars,
            partner_type="supplier",
            payment_type="outbound",
            to_pay_move_line_ids=[Command.set(debt_lines.ids)],
        )

        # Override rate: 1 USD = 1250 ARS → counterpart_rate(ARS→USD) = 1/1250
        payment.counterpart_rate = 1 / 1250.0
        payment.amount = 125_000  # 100 USD × 1250

        self._assert_currencies(payment, A=self.ars, B1=self.usd, B2=self.usd, C=self.ars)
        self._assert_rates(payment, accounting=1.0, counterpart=1 / 1250.0)
        self.assertAlmostEqual(payment.counterpart_currency_amount, 100, places=2)
        self.assertEqual(payment.to_pay_amount, 100)  # deuda en USD

        payment.action_post()

        self._assert_move_lines(
            payment,
            {
                "liquidity": {"currency": self.ars, "amt_currency": -125_000, "balance": -125_000},
                "counterpart": {"currency": self.usd, "amt_currency": 100, "balance": 125_000},
            },
        )
        self.assertIn(invoice.payment_state, ["paid", "in_payment"])

    def test_caso4_venta_de_divisa(self):
        """Caso 4 · USD → ARS → ARS  (venta de divisa)
        Pago en USD para cancelar deuda en ARS. Verifica:
        - Monedas: A = USD, B1 = B2 = C = ARS
        - counterpart_rate = rate(A→B1) = 1200 (Odoo nativo)
        - B1 = C → accounting_rate = 1/counterpart_rate (sincronización)
        - Asiento: liquidez en USD, contrapartida en ARS
        """
        invoice = self._create_invoice(120_000, self.ars, move_type="in_invoice")
        debt_lines = self._get_debt_lines(invoice)
        payment = self._create_payment(
            self.bank_usd,
            partner_type="supplier",
            payment_type="outbound",
            to_pay_move_line_ids=[Command.set(debt_lines.ids)],
        )

        # El sistema calcula counterpart_rate automáticamente
        # B1 = C = ARS → counterpart_rate = 1/accounting_rate
        expected_acc_rate = self._get_rate(self.ars, self.usd)
        expected_cp_rate = 1 / expected_acc_rate  # ≈ 1200

        self._assert_currencies(payment, A=self.usd, B1=self.ars, B2=self.ars, C=self.ars)
        self._assert_rates(payment, accounting=expected_acc_rate, counterpart=expected_cp_rate, places=2)

        # amount (manual) → 100 USD para cubrir 120 000 ARS
        payment.amount = 100

        self.assertAlmostEqual(payment.counterpart_currency_amount, 100 * expected_cp_rate, places=0)

        payment.action_post()

        expected_liq_balance = 100 / expected_acc_rate  # ≈ 120 000 ARS
        self._assert_move_lines(
            payment,
            {
                "liquidity": {"currency": self.usd, "amt_currency": -100, "balance": -expected_liq_balance},
                "counterpart": {
                    "currency": self.ars,
                    "amt_currency": expected_liq_balance,
                    "balance": expected_liq_balance,
                },
            },
        )
        self.assertIn(invoice.payment_state, ["paid", "in_payment"])

    def test_caso5_arbitraje_cruzado(self):
        """Caso 5 · USD → EUR → ARS  (3 monedas distintas)
        Pago en USD para cancelar deuda en EUR. Verifica:
        - Monedas: A = USD, B1 = B2 = EUR, C = ARS
        - counterpart_rate = rate(USD→EUR) ≈ 1.1 (por transitividad)
        - accounting_rate = rate(ARS→USD) ≈ 0.000833
        - Ambos rates visibles (A ≠ B1 Y B1 ≠ C)
        - Asiento: liquidez en USD, contrapartida en EUR, balances en ARS
        """
        invoice = self._create_invoice(100, self.eur, move_type="in_invoice")
        debt_lines = self._get_debt_lines(invoice)
        payment = self._create_payment(
            self.bank_usd,
            partner_type="supplier",
            payment_type="outbound",
            to_pay_move_line_ids=[Command.set(debt_lines.ids)],
        )

        expected_cp_rate = self._get_rate(self.usd, self.eur)  # ≈ 1.1
        expected_acc_rate = self._get_rate(self.ars, self.usd)  # ≈ 0.000833

        self._assert_currencies(payment, A=self.usd, B1=self.eur, B2=self.eur, C=self.ars)
        self._assert_rates(payment, accounting=expected_acc_rate, counterpart=expected_cp_rate, places=4)

        # amount: 100 EUR / cp_rate ≈ 90.9 USD
        expected_amount_usd = 100 / expected_cp_rate
        payment.amount = expected_amount_usd

        self.assertAlmostEqual(payment.counterpart_currency_amount, 100, places=2)

        payment.action_post()

        # Balance en ARS determinado por A→C (USD→ARS), no por B1→C (EUR→ARS)
        expected_liq_balance = expected_amount_usd / expected_acc_rate  # ≈ 109 090 ARS
        self._assert_move_lines(
            payment,
            {
                "liquidity": {
                    "currency": self.usd,
                    "amt_currency": -expected_amount_usd,
                    "balance": -expected_liq_balance,
                },
                "counterpart": {"currency": self.eur, "amt_currency": 100, "balance": expected_liq_balance},
            },
        )
        self.assertIn(invoice.payment_state, ["paid", "in_payment"])

    def test_caso6_pago_parcial(self):
        """Caso 6 · ARS → USD → ARS  (pago parcial)
        Monto del pago no cubre toda la deuda. Verifica:
        - selected_debt = total de la factura en USD
        - counterpart_currency_amount = amount × counterpart_rate < selected_debt
        - Factura queda en estado parcial o sin pagar tras postear
        """
        invoice = self._create_invoice(100, self.usd, move_type="in_invoice")
        debt_lines = self._get_debt_lines(invoice)
        payment = self._create_payment(
            self.bank_ars,
            partner_type="supplier",
            payment_type="outbound",
            amount=60_000,
            to_pay_move_line_ids=[Command.set(debt_lines.ids)],
        )

        # Rate: 1 USD = 1200 ARS (formato Odoo: ARS→USD = 1/1200)
        payment.counterpart_rate = 1 / 1200.0

        self._assert_currencies(payment, A=self.ars, B1=self.usd, B2=self.usd, C=self.ars)
        self.assertEqual(payment.selected_debt, 100, "selected_debt = deuda total en USD")
        self.assertAlmostEqual(payment.counterpart_currency_amount, 50, places=2, msg="60 000 ARS × (1/1200) = 50 USD")

        payment.action_post()

        self._assert_move_lines(
            payment,
            {
                "liquidity": {"currency": self.ars, "amt_currency": -60_000, "balance": -60_000},
                "counterpart": {"currency": self.usd, "amt_currency": 50, "balance": 60_000},
            },
        )
        self.assertIn(invoice.payment_state, ["partial", "not_paid"])

    def test_caso7_pago_anticipado(self):
        """Caso 7 · ARS → USD → ARS  (anticipo sin deuda)
        Sin factura previa, usuario elige B1 manualmente. Verifica:
        - counterpart_currency_id editable (sin deuda que lo fuerce)
        - selected_debt = 0
        - counterpart_currency_amount calculado desde rate
        - Pago se postea correctamente
        """
        payment = self._create_payment(
            self.bank_ars,
            partner_type="supplier",
            payment_type="outbound",
            amount=60_000,
        )

        # Usuario elige B1 = USD
        payment.counterpart_currency_id = self.usd
        payment.counterpart_rate = 1 / 1200.0

        self._assert_currencies(payment, A=self.ars, B1=self.usd, B2=self.usd, C=self.ars)
        self.assertEqual(payment.selected_debt, 0)
        self.assertAlmostEqual(payment.counterpart_currency_amount, 50, places=2)

        payment.action_post()

        self._assert_move_lines(
            payment,
            {
                "liquidity": {"currency": self.ars, "amt_currency": -60_000, "balance": -60_000},
                "counterpart": {"currency": self.usd, "amt_currency": 50, "balance": 60_000},
            },
        )
        self.assertIn(payment.state, ["posted", "in_process"])

    # ==================================================================
    # CASOS CON reconcile_on_company_currency (B1 ≠ B2 posible)
    # ==================================================================

    def test_caso8_reconcile_on_company_currency_ars(self):
        """Caso 8 · ARS / ARS / ARS / ARS  (reconcile fuerza B2=ARS)
        Factura en USD pero flag fuerza conciliación en ARS. Verifica:
        - B1 = B2 = C = ARS (el flag ignora la moneda de la factura)
        - selected_debt usa amount_residual (ARS), no amount_residual_currency
        - Conciliación exitosa por balance
        """
        self.company.reconcile_on_company_currency = True
        try:
            invoice = self._create_invoice(100, self.usd, move_type="in_invoice")
            payable_line = self._get_debt_lines(invoice)
            amount_ars = abs(payable_line.balance)

            payment = self._create_payment(
                self.bank_ars,
                partner_type="supplier",
                payment_type="outbound",
                amount=amount_ars,
                to_pay_move_line_ids=[Command.set(payable_line.ids)],
            )

            self._assert_currencies(payment, A=self.ars, B1=self.ars, B2=self.ars, C=self.ars)
            self.assertAlmostEqual(
                payment.selected_debt, amount_ars, places=2, msg="selected_debt en ARS (amount_residual)"
            )

            payment.action_post()

            self._assert_move_lines(
                payment,
                {
                    "liquidity": {"currency": self.ars, "amt_currency": -amount_ars, "balance": -amount_ars},
                    "counterpart": {"currency": self.ars, "amt_currency": amount_ars, "balance": amount_ars},
                },
            )
            self.assertIn(invoice.payment_state, ["paid", "in_payment"])
        finally:
            self.company.reconcile_on_company_currency = False

    def test_caso9_pago_usd_deuda_ars(self):
        """Caso 9 · USD / ARS / ARS / ARS  (pago USD, conciliación ARS)
        reconcile_on_company_currency + cuenta sin moneda. Verifica:
        - A = USD, B1 = ARS (flag fuerza company_currency), B2 = C = ARS
        - selected_debt en ARS
        """
        self.company.reconcile_on_company_currency = True
        self.account_payable.currency_id = False
        try:
            invoice = self._create_invoice(120_000, self.ars, move_type="in_invoice")
            debt_lines = self._get_debt_lines(invoice)
            payment = self._create_payment(
                self.bank_usd,
                partner_type="supplier",
                payment_type="outbound",
                amount=100,
                to_pay_move_line_ids=[Command.set(debt_lines.ids)],
            )

            self._assert_currencies(payment, A=self.usd, B1=self.ars, B2=self.ars, C=self.ars)
            self.assertEqual(payment.selected_debt, 120_000)

            expected_liq_balance = 100 / self._get_rate(self.ars, self.usd)  # ≈ 120 000

            payment.action_post()

            self._assert_move_lines(
                payment,
                {
                    "liquidity": {"currency": self.usd, "amt_currency": -100, "balance": -expected_liq_balance},
                    "counterpart": {
                        "currency": self.ars,
                        "amt_currency": expected_liq_balance,
                        "balance": expected_liq_balance,
                    },
                },
            )
            self.assertIn(invoice.payment_state, ["paid", "in_payment"])
        finally:
            self.company.reconcile_on_company_currency = False

    def test_caso10_arbitraje_informativo(self):
        """Caso 10 · EUR / USD / ARS / ARS  (3 monedas + reconcile)
        Factura USD, pago EUR, conciliación ARS. Verifica:
        - A = EUR, B1 = USD (asignado manualmente), B2 = C = ARS
        - counterpart_rate (EUR→USD) y accounting_rate (ARS→EUR) son distintos
        - Ambos rates visibles (A ≠ B1 Y B1 ≠ C)

        Con reconcile_on_company_currency el default de B1 es ARS (company),
        por lo que el usuario debe elegir manualmente B1 = USD desde la vista.
        """
        self.company.reconcile_on_company_currency = True
        try:
            invoice = self._create_invoice(100, self.usd, move_type="in_invoice")
            debt_lines = self._get_debt_lines(invoice)
            payment = self._create_payment(
                self.bank_eur,
                partner_type="supplier",
                payment_type="outbound",
                amount=100,
                to_pay_move_line_ids=[Command.set(debt_lines.ids)],
            )

            # Con reconcile_on_company_currency, B1 default = ARS.
            # El usuario override manual via el campo editable en la vista:
            payment.counterpart_currency_id = self.usd

            self._assert_currencies(payment, A=self.eur, B1=self.usd, B2=self.ars, C=self.ars)

            expected_cp = self._get_rate(self.eur, self.usd)
            expected_acc = self._get_rate(self.ars, self.eur)
            self._assert_rates(payment, accounting=expected_acc, counterpart=expected_cp, places=4)

            # Rates distintos (escenario no redundante: A ≠ B1 ≠ C)
            self.assertNotAlmostEqual(payment.counterpart_rate, payment.accounting_rate, places=4)

            expected_liq_balance = 100 / expected_acc  # ≈ 132 000 ARS
            expected_cp_amount = 100 * expected_cp  # ≈ 110 USD

            payment.action_post()

            self._assert_move_lines(
                payment,
                {
                    "liquidity": {"currency": self.eur, "amt_currency": -100, "balance": -expected_liq_balance},
                    "counterpart": {
                        "currency": self.usd,
                        "amt_currency": expected_cp_amount,
                        "balance": expected_liq_balance,
                    },
                },
            )
            self.assertIn(invoice.payment_state, ["paid", "in_payment"])
        finally:
            self.company.reconcile_on_company_currency = False

    # ==================================================================
    # TESTS DE MECÁNICA INTERNA
    # ==================================================================

    def test_sync_counterpart_rate_when_b1_eq_c(self):
        """Cuando B1 = C, counterpart_rate = 1/accounting_rate (sincronización).
        Aplica en caso 4 (USD→ARS→ARS). Modificar uno debe reflejar en el otro.
        """
        payment = self._create_payment(
            self.bank_usd,
            partner_type="supplier",
            payment_type="outbound",
            amount=100,
        )
        # B1 = ARS = C → sync activa
        self._assert_currencies(payment, A=self.usd, B1=self.ars, B2=self.ars, C=self.ars)

        acc_rate = payment.accounting_rate  # rate(C→A) = rate(ARS→USD) ≈ 0.000833
        self.assertAlmostEqual(
            payment.counterpart_rate,
            1 / acc_rate,
            places=4,
            msg="B1=C → counterpart_rate debe ser 1/accounting_rate",
        )

    def test_counterpart_currency_amount_inverse(self):
        """Modificar counterpart_currency_amount recalcula counterpart_rate.
        Spec: prioridad 1 — usuario modifica monto → recalcular tasa.
        """
        invoice = self._create_invoice(100, self.usd, move_type="in_invoice")
        payment = self._create_payment(
            self.bank_ars,
            partner_type="supplier",
            payment_type="outbound",
            amount=120_000,
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice).ids)],
        )

        # Override counterpart_currency_amount directamente → debe recalcular rate
        payment.counterpart_currency_amount = 80  # 80 USD
        # Esperado: counterpart_rate = 80 / 120_000 ≈ 0.000667
        self.assertAlmostEqual(
            payment.counterpart_rate,
            80 / 120_000,
            places=6,
            msg="inverse: counterpart_rate = counterpart_currency_amount / amount",
        )

    def test_selected_debt_uses_correct_field(self):
        """selected_debt elige amount_residual_currency o amount_residual
        según destination_currency_id vs company_currency_id.
        """
        # Factura USD → selected_debt en USD (amount_residual_currency)
        invoice_usd = self._create_invoice(100, self.usd, move_type="in_invoice")
        payment_usd = self._create_payment(
            self.bank_ars,
            partner_type="supplier",
            payment_type="outbound",
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice_usd).ids)],
        )
        self.assertEqual(payment_usd.destination_currency_id, self.usd)
        self.assertEqual(payment_usd.selected_debt, 100, "Deuda USD → selected_debt = amount_residual_currency")

        # Factura ARS → selected_debt en ARS (amount_residual)
        invoice_ars = self._create_invoice(50_000, self.ars, move_type="in_invoice")
        payment_ars = self._create_payment(
            self.bank_ars,
            partner_type="supplier",
            payment_type="outbound",
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice_ars).ids)],
        )
        self.assertEqual(payment_ars.destination_currency_id, self.ars)
        self.assertEqual(payment_ars.selected_debt, 50_000, "Deuda ARS → selected_debt = amount_residual")

    def test_rate_visibility_rules(self):
        """Regla de visibilidad de rates (spec §Cuándo mostrar cada rate).
        - counterpart_rate visible solo si A ≠ B1 Y B1 ≠ C
        - accounting_rate visible solo si A ≠ C
        """
        # Caso 1: A=B1=B2=C=ARS → ninguno visible
        p1 = self._create_payment(self.bank_ars, amount=100)
        self.assertEqual(p1.currency_id, p1.company_currency_id, "A=C → accounting_rate oculto")
        self.assertEqual(p1.currency_id, p1.counterpart_currency_id, "A=B1 → counterpart_rate oculto")

        # Caso 2: A=B1=USD, C=ARS → solo accounting_rate visible
        # Sin deuda, B1 default = company_currency. Necesitamos factura USD para que B1=USD.
        invoice_usd = self._create_invoice(100, self.usd, move_type="in_invoice")
        p2 = self._create_payment(
            self.bank_usd,
            partner_type="supplier",
            payment_type="outbound",
            amount=100,
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice_usd).ids)],
        )
        self.assertNotEqual(p2.currency_id, p2.company_currency_id, "A≠C → accounting_rate visible")
        self.assertEqual(p2.currency_id, p2.counterpart_currency_id, "A=B1 → counterpart_rate oculto")

        # Caso 5: A=USD, B1=EUR, C=ARS → ambos visibles
        invoice_eur = self._create_invoice(100, self.eur, move_type="in_invoice")
        p5 = self._create_payment(
            self.bank_usd,
            partner_type="supplier",
            payment_type="outbound",
            to_pay_move_line_ids=[Command.set(self._get_debt_lines(invoice_eur).ids)],
        )
        self.assertNotEqual(p5.currency_id, p5.company_currency_id, "A≠C → accounting_rate visible")
        self.assertNotEqual(p5.currency_id, p5.counterpart_currency_id, "A≠B1")
        self.assertNotEqual(p5.counterpart_currency_id, p5.company_currency_id, "B1≠C → counterpart_rate visible")
