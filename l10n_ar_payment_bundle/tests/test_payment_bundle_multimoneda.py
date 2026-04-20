"""
Tests para l10n_ar_payment_bundle — modelo tri-monetario
=========================================================

Validan que el bundle funciona correctamente con el modelo tri-monetario
de account_payment_pro, incluyendo pagos multimoneda y retenciones.

Principios de diseño del bundle (spec_l10n_ar_payment_bundle.md):
    P1 — El pago principal define B (moneda de cancelación).
    P2 — Los linked heredan B del principal; no lo pueden editar.
         Cada linked computa su propio counterpart_rate según su diario.
    P3 — Cualquier diario es válido para pagos vinculados (no solo ARS).

Estructura de un bundle:
    Main payment: is_main_payment=True, amount=0, journal=bundle_journal.
    Linked payments: main_payment_id=main, journal=cualquiera, amount>0.

    Main concentra: deuda, retenciones, write-off.
    Linked aportan: efectivo/cheques/transferencias expresados en B vía
                    counterpart_currency_amount.

Convención de monedas (heredada de spec.md):
    A  = currency_id              — moneda del diario (varía por linked)
    B  = destination_currency_id  — moneda de cancelación (fijada por main)
    C  = company_currency_id      — ARS

Rates de referencia:
    1 USD = 1 200 ARS
    1 EUR = 1 320 ARS
"""

from odoo import Command
from odoo.addons.l10n_ar_tax.tests.test_payment_withholding_multimoneda import (
    TestPaymentWithholdingMultimoneda,
)
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPaymentBundle(TestPaymentWithholdingMultimoneda):
    """Tests de bundles multimoneda con retenciones."""

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Diario caja ARS (tipo cash, para diferenciar de bank_ars)
        cls.cash_ars = cls.env["account.journal"].create(
            {
                "name": "Caja ARS",
                "type": "cash",
                "code": "CARS",
                "company_id": cls.company.id,
                "currency_id": cls.ars.id,
            }
        )

        # Diario bundle: ya creado por el template ar_ri, lo buscamos en lugar de crear uno nuevo.
        # payment_bundle es mode="unique", por lo que no puede existir en más de un diario.
        cls.bundle_journal = cls.env["account.journal"].search(
            [
                ("outbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
                ("company_id", "=", cls.company.id),
            ],
            limit=1,
        )
        assert cls.bundle_journal, "El template ar_ri debe haber creado el diario bundle"

        # Payment method line del bundle para outbound
        cls.bundle_pml_out = cls.bundle_journal.outbound_payment_method_line_ids.filtered(
            lambda l: l.code == "payment_bundle"
        )

        # Agregar método cheques propios a banco ARS (para B.4)
        own_checks_method = cls.env.ref("l10n_latam_check.account_payment_method_own_checks")
        for journal in (cls.bank_ars, cls.bank_usd):
            already = journal.outbound_payment_method_line_ids.filtered(lambda l: l.code == "own_checks")
            if not already:
                journal.write(
                    {
                        "outbound_payment_method_line_ids": [
                            Command.create({"payment_method_id": own_checks_method.id})
                        ],
                    }
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_main_payment(self, invoice, fiscal_position=None, **kw):
        """Crea el pago principal del bundle (amount=0, is_main_payment=True).

        Retorna el pago en borrador con deuda seleccionada y retenciones computadas.
        """
        fp = fiscal_position or self.fp_iibb
        debt = invoice.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        vals = {
            "journal_id": self.bundle_journal.id,
            "partner_id": self.partner.id,
            "partner_type": "supplier",
            "payment_type": "outbound",
            "payment_method_line_id": self.bundle_pml_out.id,
            "date": self.today,
            "amount": 0,
            "l10n_ar_fiscal_position_id": fp.id,
            "to_pay_move_line_ids": [Command.set(debt.ids)],
        }
        vals.update(kw)
        return self.env["account.payment"].create(vals)

    def _add_linked_payment(self, main_payment, journal, amount, **kw):
        """Agrega un pago vinculado al bundle.

        Simula el flujo de la UI: el linked hereda counterpart_currency_id
        del main vía default de contexto, y computa su propio counterpart_rate.
        """
        vals = {
            "journal_id": journal.id,
            "partner_id": main_payment.partner_id.id,
            "partner_type": main_payment.partner_type,
            "payment_type": main_payment.payment_type,
            "date": self.today,
            "amount": amount,
            "main_payment_id": main_payment.id,
            "company_id": main_payment.company_id.id,
        }
        vals.update(kw)
        return (
            self.env["account.payment"]
            .with_context(default_counterpart_currency_id=main_payment.counterpart_currency_id.id)
            .create(vals)
        )

    def _add_linked_check_payment(self, main_payment, journal, checks, **kw):
        """Agrega un pago vinculado con cheques propios."""
        own_checks_pml = journal.outbound_payment_method_line_ids.filtered(lambda l: l.code == "own_checks")
        vals = {
            "journal_id": journal.id,
            "partner_id": main_payment.partner_id.id,
            "partner_type": main_payment.partner_type,
            "payment_type": main_payment.payment_type,
            "payment_method_line_id": own_checks_pml.id,
            "date": self.today,
            "main_payment_id": main_payment.id,
            "company_id": main_payment.company_id.id,
            "l10n_latam_new_check_ids": [
                Command.create(
                    {
                        "name": c["name"],
                        "payment_date": c.get("payment_date", self.today),
                        "amount": c["amount"],
                    }
                )
                for c in checks
            ],
        }
        vals.update(kw)
        return (
            self.env["account.payment"]
            .with_context(default_counterpart_currency_id=main_payment.counterpart_currency_id.id)
            .create(vals)
        )

    # ==================================================================
    # B.1 — Bundle local simple (A=B=C=ARS)
    # ==================================================================

    def test_b1_bundle_ars_simple(self):
        """B.1 · Factura 12 100 ARS (10 000 neto). Bundle: caja 5 000 + banco 7 100.
        Sin retenciones (sin fiscal position).

        Verifica:
        - Main: is_main_payment, amount=0, B=ARS
        - Linked: counterpart_currency_id=ARS (heredado del main)
        - payment_total del main = suma linked = 12 100
        - payment_difference = 0 (deuda totalmente cubierta)
        - Post: asientos de linked balancean, main sin asiento (bypass)
        """
        invoice = self._create_invoice(10_000, self.ars)
        self.assertAlmostEqual(invoice.amount_total, 12_100, places=2)

        main = self._create_main_payment(
            invoice,
            fiscal_position=False,
            l10n_ar_fiscal_position_id=False,
        )
        self.assertTrue(main.is_main_payment)
        self.assertEqual(main.amount, 0)
        self.assertEqual(main.destination_currency_id, self.ars, "B = ARS")

        linked1 = self._add_linked_payment(main, self.cash_ars, 5_000)
        linked2 = self._add_linked_payment(main, self.bank_ars, 7_100)

        # Linked heredan B del main
        self.assertEqual(linked1.counterpart_currency_id, self.ars)
        self.assertEqual(linked2.counterpart_currency_id, self.ars)

        # counterpart_currency_amount = amount (A=B=ARS)
        self.assertAlmostEqual(linked1.counterpart_currency_amount, 5_000, places=2)
        self.assertAlmostEqual(linked2.counterpart_currency_amount, 7_100, places=2)

        # payment_total del main incluye linked payments
        self.assertAlmostEqual(main.payment_total, 12_100, places=2)

        # payment_difference de cada linked = 0 (deuda cubierta)
        self.assertAlmostEqual(
            linked1.payment_difference,
            0,
            places=2,
            msg="12100 - (5000+7100) - 0 - 0 = 0",
        )

        # Post
        main.action_post()
        for linked in (linked1, linked2):
            self.assertIn(linked.state, ("paid", "in_process"), "Linked payment debe estar posteado")
            self.assertAlmostEqual(
                sum(linked.move_id.line_ids.mapped("balance")),
                0,
                places=2,
                msg="Partida doble en linked",
            )

    # ==================================================================
    # B.2 — Bundle ARS con retención IIBB (A=B=C=ARS)
    # ==================================================================

    def test_b2_bundle_ars_con_retencion(self):
        """B.2 · Factura 12 100 ARS (10 000 neto). Bundle: caja 5 000 +
        banco 6 800 + retención IIBB 3% = 300 ARS.

        Verifica:
        - Retención: base=10 000, amount=300 ARS
        - withholdings_amount = 300 ARS (en B=ARS)
        - payment_total = 5000 + 6800 + 300 = 12 100
        - payment_difference = 0
        - Post: todos los asientos balancean
        """
        invoice = self._create_invoice(10_000, self.ars)
        main = self._create_main_payment(invoice)

        # Verificar retención
        wth = self._wth_line(main)
        self.assertAlmostEqual(wth.base_amount, 10_000, places=2)
        self.assertAlmostEqual(wth.amount, 300, places=2)
        self.assertAlmostEqual(main.withholdings_amount, 300, places=2)

        # El main tiene amount=0, por lo tanto counterpart_currency_amount=0.
        # Las retenciones fluyen a payment_total vía withholdings_amount (override l10n_ar_tax).
        self.assertAlmostEqual(main.counterpart_currency_amount, 0, places=2)

        # Linked: caja + banco que cubran deuda - retención
        linked1 = self._add_linked_payment(main, self.cash_ars, 5_000)
        linked2 = self._add_linked_payment(main, self.bank_ars, 6_800)

        # payment_total = linked_totals + main wth+wo
        self.assertAlmostEqual(main.payment_total, 12_100, places=2)
        self.assertAlmostEqual(linked1.payment_difference, 0, places=2)

        # Post
        main.action_post()
        for linked in (linked1, linked2):
            self.assertIn(linked.state, ("paid", "in_process"), "Linked payment debe estar posteado")

        # Main genera asiento (tiene withholdings)
        self.assertTrue(main.move_id, "Main con retenciones genera asiento")
        wth_ml = self._wth_move_lines(main)
        self.assertAlmostEqual(abs(wth_ml.balance), 300, places=2)

    # ==================================================================
    # B.3 — Bundle deuda USD, linked mixtos ARS + USD (A≠B para ARS linked)
    # ==================================================================

    def test_b3_bundle_deuda_usd_linked_mixtos(self):
        """B.3 · Factura 1 210 USD (1 000 neto, 1 USD = 1 200 ARS).
        Bundle: linked banco USD 500 + linked banco ARS 600 000 + retención IIBB.

        Verifica:
        - Main: B = USD
        - Linked USD: A=B=USD, counterpart_rate=1.0, cca=500 USD
        - Linked ARS: A=ARS, B=USD, counterpart_rate≈0.000833, cca=500 USD
        - Retención: base=1 200 000 ARS, amount=36 000 ARS, en B≈30 USD
        - payment_total en USD
        - Todos los asientos balancean
        """
        invoice = self._create_invoice(1_000, self.usd)
        main = self._create_main_payment(invoice)

        self.assertEqual(main.destination_currency_id, self.usd, "B = USD")

        # Retención: base_amount en C(ARS), withholdings_amount en B(USD)
        wth = self._wth_line(main)
        self.assertAlmostEqual(wth.base_amount, 1_200_000, places=0)
        self.assertAlmostEqual(wth.amount, 36_000, places=0)
        self.assertAlmostEqual(main.withholdings_amount, 30, places=2)

        # Linked 1: banco USD (A=B=USD)
        linked_usd = self._add_linked_payment(main, self.bank_usd, 500)
        self.assertEqual(linked_usd.currency_id, self.usd, "Linked USD: A=USD")
        self.assertEqual(linked_usd.counterpart_currency_id, self.usd, "Linked USD: B=USD")
        self.assertAlmostEqual(
            linked_usd.counterpart_rate,
            1.0,
            places=6,
            msg="A=B → counterpart_rate=1.0",
        )
        self.assertAlmostEqual(
            linked_usd.counterpart_currency_amount,
            500,
            places=2,
        )

        # Linked 2: banco ARS (A=ARS, B=USD)
        linked_ars = self._add_linked_payment(main, self.bank_ars, 600_000)
        self.assertEqual(linked_ars.currency_id, self.ars, "Linked ARS: A=ARS")
        self.assertEqual(linked_ars.counterpart_currency_id, self.usd, "Linked ARS: B=USD")
        expected_cp_rate = self._get_rate(self.ars, self.usd)  # ≈ 0.000833
        self.assertAlmostEqual(
            linked_ars.counterpart_rate,
            expected_cp_rate,
            places=6,
            msg="Linked ARS computa su propio counterpart_rate (ARS→USD)",
        )
        expected_cca = 600_000 * expected_cp_rate  # ≈ 500 USD
        self.assertAlmostEqual(
            linked_ars.counterpart_currency_amount,
            expected_cca,
            places=2,
        )

        # payment_total del main en USD
        expected_total = (
            linked_usd.counterpart_currency_amount + linked_ars.counterpart_currency_amount + main.withholdings_amount
        )
        self.assertAlmostEqual(
            main.payment_total,
            expected_total,
            places=2,
            msg="payment_total = sum(linked cca) + withholdings, todo en B(USD)",
        )

        # Post
        main.action_post()
        for linked in (linked_usd, linked_ars):
            self.assertIn(linked.state, ("paid", "in_process"), "Linked payment debe estar posteado")
            lines = linked.move_id.line_ids
            self.assertAlmostEqual(
                sum(lines.mapped("balance")),
                0,
                places=2,
                msg=f"Partida doble en linked {linked.journal_id.code}",
            )

        # Main genera asiento (tiene retenciones)
        self.assertTrue(main.move_id)
        wth_ml = self._wth_move_lines(main)
        self.assertAlmostEqual(abs(wth_ml.balance), 36_000, places=0)

        # Pago intencional parcial: 500+500+30 = 1030 USD de 1210 USD total
        self.assertEqual(invoice.payment_state, "partial", "1030 USD pagados de 1210 USD → debe quedar parcial")

    def test_b3_linked_usd_uses_forced_main_counterpart_rate(self):
        """B.3.x · Main con deuda USD y counterpart rate forzado.

        Caso de regresión:
        - Main: A=ARS, B=USD, se fuerza user_counterpart_rate=1400 (en vez de tasa vigente)
        - Linked USD: A=B=USD

        Verifica:
        - linked.accounting_rate toma la tasa forzada del main (USD/ARS = 1/1400)
        - no toma la tasa contable de mercado del día
        """
        invoice = self._create_invoice(1_000, self.usd)
        main = self._create_main_payment(invoice, fiscal_position=False, l10n_ar_fiscal_position_id=False)

        forced_user_rate = 1_400.0
        forced_counterpart_rate = 1.0 / forced_user_rate
        market_counterpart_rate = self._get_rate(self.ars, self.usd)

        self.assertNotAlmostEqual(
            forced_counterpart_rate,
            market_counterpart_rate,
            places=9,
            msg="Precondición: la tasa forzada debe diferir de la tasa de mercado",
        )

        main.counterpart_rate = forced_counterpart_rate
        self.assertAlmostEqual(main.counterpart_rate, forced_counterpart_rate, places=9)

        linked_usd = self._add_linked_payment(main, self.bank_usd, 100)
        self.assertEqual(linked_usd.currency_id, self.usd)
        self.assertEqual(linked_usd.counterpart_currency_id, self.usd)
        self.assertAlmostEqual(linked_usd.counterpart_rate, 1.0, places=9, msg="A=B en linked USD")

        self.assertAlmostEqual(
            linked_usd.accounting_rate,
            forced_counterpart_rate,
            places=9,
            msg="El linked USD debe respetar la tasa forzada en el main",
        )
        self.assertNotAlmostEqual(
            linked_usd.accounting_rate,
            market_counterpart_rate,
            places=9,
            msg="No debe usar la tasa contable de mercado",
        )
        self.assertAlmostEqual(linked_usd.user_accounting_rate, forced_user_rate, places=6)

    def test_b4_bundle_deuda_usd_cheques_ars_y_transfer_usd(self):
        """B.4 · Factura 1 210 USD (1 000 neto, 1 USD = 1 200 ARS).
        Bundle: 2 cheques propios ARS + 1 transferencia USD + retención IIBB.

        Verifica:
        - Linked cheques ARS: A=ARS, B=USD, 2 cheques generan 2 liq lines
        - Linked USD: A=B=USD, transferencia normal
        - Retención: 36 000 ARS = 30 USD
        - Todos los asientos balancean
        """
        invoice = self._create_invoice(1_000, self.usd)
        main = self._create_main_payment(invoice)

        self.assertAlmostEqual(main.withholdings_amount, 30, places=2)

        # Linked 1: 2 cheques propios ARS (sumando ~580 USD ≈ 696 000 ARS)
        linked_checks = self._add_linked_check_payment(
            main,
            self.bank_ars,
            [
                {"name": "B0000100", "amount": 400_000},
                {"name": "B0000101", "amount": 296_000},
            ],
        )
        self.assertEqual(linked_checks.currency_id, self.ars, "Cheques en ARS")
        self.assertEqual(
            linked_checks.counterpart_currency_id,
            self.usd,
            "B=USD heredado del main",
        )
        self.assertAlmostEqual(linked_checks.amount, 696_000, places=2)

        # counterpart_currency_amount en USD
        expected_cp_rate = self._get_rate(self.ars, self.usd)
        expected_checks_in_b = 696_000 * expected_cp_rate  # ≈ 580 USD
        self.assertAlmostEqual(
            linked_checks.counterpart_currency_amount,
            expected_checks_in_b,
            places=2,
        )

        # Linked 2: transferencia USD (cubre el resto ≈ 600 USD)
        remaining_usd = 1_210 - expected_checks_in_b - 30  # ≈ 600 USD
        linked_usd = self._add_linked_payment(
            main,
            self.bank_usd,
            self.usd.round(remaining_usd),
        )
        self.assertEqual(linked_usd.currency_id, self.usd)
        self.assertAlmostEqual(
            linked_usd.counterpart_rate,
            1.0,
            places=6,
        )

        # Post
        main.action_post()

        # Linked cheques: 2 cheques → 2 líneas de liquidez
        check_lines = linked_checks.move_id.line_ids
        liq_lines = check_lines.filtered(lambda l: l.account_id == linked_checks.outstanding_account_id)
        self.assertEqual(len(liq_lines), 2, "2 cheques → 2 líneas de liquidez")

        # Contrapartida del linked cheques en USD (B)
        cp_check = check_lines.filtered(lambda l: l.account_id == linked_checks.destination_account_id)
        self.assertEqual(cp_check.currency_id, self.usd, "Contrapartida en USD")
        self.assertAlmostEqual(
            sum(check_lines.mapped("balance")),
            0,
            places=2,
            msg="Partida doble linked cheques",
        )

        # Linked USD: asiento normal
        usd_lines = linked_usd.move_id.line_ids
        self.assertAlmostEqual(
            sum(usd_lines.mapped("balance")),
            0,
            places=2,
            msg="Partida doble linked USD",
        )

        # Main: retención
        self.assertTrue(main.move_id)
        wth_ml = self._wth_move_lines(main)
        self.assertAlmostEqual(abs(wth_ml.balance), 36_000, places=0)

    # ==================================================================
    # B.5 — Bundle deuda EUR: linked ARS + linked USD (arbitraje)
    # ==================================================================

    def test_b5_bundle_deuda_eur_arbitraje(self):
        """B.5 · Factura 1 320 EUR (≈ 1 000 neto, 1 EUR = 1 320 ARS).
        Bundle: linked ARS + linked USD + retención IIBB.

        Verifica:
        - Main: B = EUR
        - Linked ARS: A=ARS, B=EUR, counterpart_rate = _get_rate(ARS, EUR)
        - Linked USD: A=USD, B=EUR, counterpart_rate = _get_rate(USD, EUR)
        - Retención: base = neto_EUR × withholding_rate → en ARS
        - Cada linked computa su propio counterpart_rate
        - Todos los asientos balancean
        """
        invoice = self._create_invoice(1_000, self.eur)
        main = self._create_main_payment(invoice)

        self.assertEqual(main.destination_currency_id, self.eur, "B = EUR")

        # Retención en C=ARS: base = 1000 EUR × (C/B rate)
        wth_rate = main._get_withholding_rate()
        # C/B = ARS/EUR = 1320
        self.assertAlmostEqual(wth_rate, 1_320, places=0)

        wth = self._wth_line(main)
        self.assertAlmostEqual(wth.base_amount, 1_000 * 1_320, places=0)
        wth_amount_ars = wth.amount  # ≈ 39 600 ARS
        wth_amount_eur = main.withholdings_amount  # ≈ 30 EUR

        # Linked ARS: ~800 000 ARS
        linked_ars = self._add_linked_payment(main, self.bank_ars, 800_000)
        self.assertEqual(linked_ars.counterpart_currency_id, self.eur)
        cp_rate_ars_eur = self._get_rate(self.ars, self.eur)
        self.assertAlmostEqual(
            linked_ars.counterpart_rate,
            cp_rate_ars_eur,
            places=6,
            msg="Linked ARS: propio rate ARS→EUR",
        )
        linked_ars_in_eur = 800_000 * cp_rate_ars_eur  # ≈ 606.06 EUR
        self.assertAlmostEqual(
            linked_ars.counterpart_currency_amount,
            linked_ars_in_eur,
            places=2,
        )

        # Linked USD: lo que falte en EUR, expresado en USD
        remaining_eur = self.eur.round(
            1_210 * 1.21 / 1.21  # invoice.amount_total in EUR  ← simplificamos
        )
        # Mejor: calculamos cuánto falta en EUR
        total_needed_eur = main.selected_debt  # = 1210 EUR (total con IVA)
        remaining_eur = total_needed_eur - linked_ars_in_eur - wth_amount_eur
        cp_rate_usd_eur = self._get_rate(self.usd, self.eur)  # ≈ 1.1

        amount_usd = self.usd.round(remaining_eur / cp_rate_usd_eur)
        linked_usd = self._add_linked_payment(main, self.bank_usd, amount_usd)

        self.assertEqual(linked_usd.counterpart_currency_id, self.eur)
        self.assertAlmostEqual(
            linked_usd.counterpart_rate,
            cp_rate_usd_eur,
            places=6,
            msg="Linked USD: propio rate USD→EUR (≈1.1)",
        )

        # payment_total en EUR
        expected_total = (
            linked_ars.counterpart_currency_amount + linked_usd.counterpart_currency_amount + wth_amount_eur
        )
        self.assertAlmostEqual(
            main.payment_total,
            expected_total,
            places=2,
            msg="payment_total = todo en EUR (B)",
        )

        # Post
        main.action_post()
        for linked in (linked_ars, linked_usd):
            self.assertIn(linked.state, ("paid", "in_process"), "Linked payment debe estar posteado")
            lines = linked.move_id.line_ids
            self.assertAlmostEqual(
                sum(lines.mapped("balance")),
                0,
                places=2,
                msg=f"Partida doble linked {linked.journal_id.code}",
            )

        # Main: retención en ARS
        wth_ml = self._wth_move_lines(main)
        self.assertAlmostEqual(abs(wth_ml.balance), wth_amount_ars, places=0)

    # ==================================================================
    # B.6 — Constraint integridad de moneda en linked payments
    # ==================================================================

    def test_b6_constrains_currency_consistency(self):
        """B.6 · Verifica que no se pueda confirmar un linked payment con
        counterpart_currency_id distinto al del main payment.

        La validación se ejecuta en action_post (no al crear), porque al
        crear desde la UI el main_payment aún no persistió su
        counterpart_currency_id y la comparación contra DB daría falso
        positivo.
        """
        invoice = self._create_invoice(1_000, self.usd)
        main = self._create_main_payment(invoice, fiscal_position=False, l10n_ar_fiscal_position_id=False)
        self.assertEqual(main.counterpart_currency_id, self.usd)

        # Forzamos counterpart_currency_id=ARS en un bundle con B=USD
        linked = self._add_linked_payment(
            main,
            self.bank_ars,
            amount=1_000,
            counterpart_currency_id=self.ars.id,
        )

        with self.assertRaisesRegex(ValidationError, "The counterpart currency of a linked payment must match"):
            linked._check_bundle_currency_consistency()

    # ==================================================================
    # B.7 — Bundle reconcile (A=C=ARS, B1=USD, B2=ARS) + IIBB
    # ==================================================================

    def test_b7_bundle_reconcile_ars_journal_usd_invoice(self):
        """B.7 · caso 8 (reconcile_on_company_currency=True): A=C=ARS, B1=USD, B2=ARS.
        Factura 1 000 USD neto (= 1 200 000 ARS neto, rate 1 200 ARS/USD).
        Bundle: linked banco ARS + retención IIBB 3%.

        En modo reconcile:
            destination_currency_id (B2) = ARS (company currency)
            counterpart_currency_id (B1) = USD (moneda de la deuda)
            B1 ≠ B2 → _compute_payment_difference mezclaría monedas
                       si usa counterpart_currency_amount (B1) vs selected_debt (B2).

        Verifica:
            - selected_debt en ARS (B2=C): 1 452 000 ARS
            - wth base = 1 200 000 ARS, wth amount = 36 000 ARS
            - withholdings_amount = 36 000 ARS (en B2=ARS)
            - Linked ARS: amount 1 416 000, cca 1 416 000 ARS
            - payment_difference = 0 (sin mezcla de monedas)
            - Todos los asientos balancean
        """
        self.company.reconcile_on_company_currency = True
        self.addCleanup(setattr, self.company, "reconcile_on_company_currency", False)

        invoice = self._create_invoice(1_000, self.usd)
        self.assertAlmostEqual(invoice.amount_total, 1_210, places=2)

        main = self._create_main_payment(invoice)

        # En reconcile el main toma B2=ARS como destination_currency_id
        self.assertEqual(main.destination_currency_id, self.ars, "B2=ARS en reconcile mode")

        # El main puede tener B1=USD si el usuario lo seleccionó (editable en modo reconcile)
        main.counterpart_currency_id = self.usd

        # selected_debt en ARS (B2=C → amount_residual)
        # Factura 1210 USD × 1200 = 1 452 000 ARS
        self.assertAlmostEqual(main.selected_debt, 1_452_000, places=0)

        # Retención: B2=ARS → _get_withholding_rate=1.0, base y amount en ARS
        wth = self._wth_line(main)
        self.assertAlmostEqual(wth.base_amount, 1_200_000, places=0)
        self.assertAlmostEqual(wth.amount, 36_000, places=0)
        self.assertAlmostEqual(main.withholdings_amount, 36_000, places=0, msg="withholdings_amount en ARS (B2=C)")

        # Linked banco ARS: paga la deuda neta = 1 452 000 - 36 000 = 1 416 000 ARS
        linked = self._add_linked_payment(main, self.bank_ars, 1_416_000)

        # El linked hereda counterpart_currency_id=USD (B1) del main, así que
        # counterpart_currency_amount está en B1=USD (≈ 1180 USD), no en ARS.
        # Lo relevante para la partida doble es payment_total, que usa el branch
        # B1≠B2 y convierte A→C: amount_ARS / accounting_rate(1.0) = 1 416 000 ARS.
        self.assertAlmostEqual(linked.payment_total, 1_416_000, places=0)

        # payment_total del main = sum(linked.payment_total) + withholdings = 1416000 + 36000 = 1452000 ARS
        self.assertAlmostEqual(main.payment_total, 1_452_000, places=0)

        # payment_difference = selected_debt - payment_total = 0
        # Si B1≠B2 se mezclan monedas, el resultado sería incorrecto (≠ 0)
        self.assertAlmostEqual(
            linked.payment_difference, 0, places=0, msg="payment_difference debe ser 0 (sin mezcla B1 vs B2)"
        )

        # Post
        main.action_post()
        self.assertIn(linked.state, ("paid", "in_process"), "Linked debe estar posteado")

        # Asiento del linked balancear
        self.assertAlmostEqual(
            sum(linked.move_id.line_ids.mapped("balance")),
            0,
            places=2,
            msg="Partida doble en linked",
        )

        # Asiento del main (retención) balancear
        self.assertTrue(main.move_id, "Main con retenciones debe generar asiento")
        self.assertAlmostEqual(
            sum(main.move_id.line_ids.mapped("balance")),
            0,
            places=2,
            msg="Partida doble en main",
        )
        wth_ml = self._wth_move_lines(main)
        self.assertAlmostEqual(abs(wth_ml.balance), 36_000, places=0)
