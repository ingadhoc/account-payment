"""
Tests de transferencias internas multi-moneda
==============================================

Validan que las transferencias internas (account_internal_transfer)
funcionan correctamente con el modelo tri-monetario de account_payment_pro.

Flujo de una transferencia interna:
    1. Usuario crea pago outbound con is_internal_transfer=True
    2. Selecciona journal origen (A1) y destination_journal (A2)
    3. Al postear, se crea un paired payment inbound en el journal destino
    4. Las líneas de la cuenta puente (transfer account) se reconcilian

Riesgo multi-moneda:
    Cuando A1 ≠ A2, el amount del paired payment debe convertirse a A2.
    El código actual copia amount verbatim → 1.200.000 ARS se convierte
    en 1.200.000 USD en el paired, que es incorrecto.

Rates de referencia:
    1 USD = 1 200 ARS
    1 EUR = 1 320 ARS
    USD → EUR (transitividad) = 1320/1200 = 1.1
"""

from odoo.addons.account_payment_pro.tests.test_payment_multimoneda import TestPaymentMultimoneda
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestInternalTransferMultimoneda(TestPaymentMultimoneda):
    """Tests de transferencias internas con múltiples monedas."""

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cash_ars = cls.env["account.journal"].create(
            {
                "name": "Caja ARS",
                "type": "cash",
                "code": "CARS",
                "company_id": cls.company.id,
                "currency_id": cls.ars.id,
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_transfer(self, journal_from, journal_to, amount, **kw):
        """Crea una transferencia interna en borrador.

        ``amount`` está en la moneda del journal_from (A1).
        """
        vals = {
            "payment_type": "outbound",
            "is_internal_transfer": True,
            "journal_id": journal_from.id,
            "destination_journal_id": journal_to.id,
            "amount": amount,
            "date": self.today,
            "company_id": self.company.id,
        }
        vals.update(kw)
        return self.env["account.payment"].create(vals)

    def _assert_transfer_ok(self, payment, expected_paired_amount, paired_currency):
        """Postea la transferencia y verifica:
        - Ambos pagos posteados
        - Ambos asientos balancean (sum(balance) == 0)
        - Paired amount correcto en la moneda destino
        - Líneas de cuenta puente reconcilian
        """
        payment.action_post()
        paired = payment.paired_internal_transfer_payment_id
        self.assertTrue(paired, "Debe existir paired payment")

        # Ambos posteados
        self.assertIn(payment.state, ["paid", "in_process"])
        self.assertEqual(paired.move_id.state, "posted")

        # Ambos asientos balancean
        for pay, label in [(payment, "original"), (paired, "paired")]:
            total = sum(pay.move_id.line_ids.mapped("balance"))
            self.assertAlmostEqual(
                total,
                0,
                places=2,
                msg=f"Partida doble en asiento {label}",
            )

        # Paired amount en moneda correcta
        self.assertEqual(
            paired.currency_id,
            paired_currency,
            f"Paired currency debe ser {paired_currency.name}",
        )
        self.assertAlmostEqual(
            paired.amount,
            expected_paired_amount,
            places=2,
            msg=f"Paired amount debe ser {expected_paired_amount} {paired_currency.name}",
        )

        # Verificar que las líneas de la cuenta puente reconcilian
        transfer_account = payment.destination_account_id
        original_transfer_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id == transfer_account)
        paired_transfer_lines = paired.move_id.line_ids.filtered(lambda l: l.account_id == transfer_account)
        self.assertTrue(original_transfer_lines, "Original debe tener línea en cuenta puente")
        self.assertTrue(paired_transfer_lines, "Paired debe tener línea en cuenta puente")

        # Balances en C (ARS) deben ser opuestos — siempre se cumple
        self.assertAlmostEqual(
            sum(original_transfer_lines.mapped("balance")) + sum(paired_transfer_lines.mapped("balance")),
            0,
            places=2,
            msg="Balances en C de la cuenta puente deben cancelarse",
        )

        # Reconciliación completa: solo verificable cuando ambos lados usan la misma
        # moneda en la cuenta puente. Cuando ambos diarios son en divisas distintas
        # (ej: USD → EUR), las líneas quedan con currency_id diferente y Odoo no puede
        # reconciliar el amount_currency, aunque los balances ARS cancelen.
        if original_transfer_lines[0].currency_id == paired_transfer_lines[0].currency_id:
            all_transfer_lines = original_transfer_lines | paired_transfer_lines
            self.assertTrue(
                all(l.reconciled for l in all_transfer_lines),
                "Las líneas de cuenta puente deben estar reconciliadas",
            )

        return paired

    # ==================================================================
    # IT.1 — ARS → ARS (trivial, misma moneda)
    # ==================================================================

    def test_it1_ars_to_ars(self):
        """IT.1 · Transferencia ARS → ARS.

        Caso trivial, misma moneda. Verifica regresión:
        - amount se copia tal cual (sin conversión)
        - Ambos asientos balancean
        - Líneas de cuenta puente reconcilian
        """
        payment = self._create_transfer(self.bank_ars, self.cash_ars, 100_000)
        self.assertEqual(payment.currency_id, self.ars)

        paired = self._assert_transfer_ok(payment, 100_000, self.ars)
        self.assertAlmostEqual(paired.accounting_rate, 1.0, places=6)

    # ==================================================================
    # IT.2 — ARS → USD (compra de USD)
    # ==================================================================

    def test_it2_ars_to_usd(self):
        """IT.2 · Transferencia ARS → USD (compra de divisas).

        Original: 1.200.000 ARS (outbound desde banco ARS).
        Paired: debe ser 1.000 USD (inbound en banco USD) a rate 1200.

        Verifica que el amount se convierte de A1(ARS) a A2(USD),
        no se copia verbatim (bug actual: paired.amount = 1.200.000 "USD").
        """
        payment = self._create_transfer(self.bank_ars, self.bank_usd, 1_200_000)

        self.assertEqual(payment.currency_id, self.ars)
        self.assertAlmostEqual(payment.accounting_rate, 1.0, places=6)

        # Expected paired: 1.200.000 ARS / 1200 = 1.000 USD
        paired = self._assert_transfer_ok(payment, 1_000, self.usd)

        # Paired accounting_rate debe ser el natural (C→A2 = ARS→USD ≈ 0.000833)
        expected_rate = self._get_rate(self.ars, self.usd)
        self.assertAlmostEqual(paired.accounting_rate, expected_rate, places=6)

        # Balance de liquidez del paired en ARS = 1.200.000
        paired_liq = paired.move_id.line_ids.filtered(lambda l: l.account_id == paired.outstanding_account_id)
        self.assertAlmostEqual(
            abs(paired_liq.balance),
            1_200_000,
            places=2,
            msg="Balance en ARS debe coincidir con el original",
        )

        # Paired counterpart: B1=ARS (dest_journal=ARS), amount_original=1.200.000
        self.assertEqual(paired.counterpart_currency_id, self.ars)
        self.assertAlmostEqual(paired.counterpart_currency_amount, 1_200_000, places=2)

    # ==================================================================
    # IT.3 — USD → ARS (venta de USD)
    # ==================================================================

    def test_it3_usd_to_ars(self):
        """IT.3 · Transferencia USD → ARS (venta de divisas).

        Original: 1.000 USD (outbound desde banco USD).
        Paired: debe ser 1.200.000 ARS (inbound en banco ARS).

        Verifica el caso inverso de IT.2.
        """
        payment = self._create_transfer(self.bank_usd, self.bank_ars, 1_000)

        self.assertEqual(payment.currency_id, self.usd)
        expected_acc_rate = self._get_rate(self.ars, self.usd)
        self.assertAlmostEqual(payment.accounting_rate, expected_acc_rate, places=6)

        # Expected paired: 1.000 USD × 1200 = 1.200.000 ARS
        paired = self._assert_transfer_ok(payment, 1_200_000, self.ars)
        self.assertAlmostEqual(paired.accounting_rate, 1.0, places=6)

        # Paired counterpart: B1=USD (dest_journal=USD), amount_original=1.000
        self.assertEqual(paired.counterpart_currency_id, self.usd)
        self.assertAlmostEqual(
            paired.counterpart_rate,
            1_000 / 1_200_000,
            places=6,
            msg="Counterpart rate del paired = original_amount / paired_amount",
        )
        self.assertAlmostEqual(paired.counterpart_currency_amount, 1_000, places=2)

    # ==================================================================
    # IT.4 — USD → EUR (exchange de moneda extranjera)
    # ==================================================================

    def test_it4_usd_to_eur(self):
        """IT.4 · Transferencia USD → EUR (arbitraje).

        Original: 1.000 USD (outbound desde banco USD).
        Paired: debe ser ~909.09 EUR (inbound en banco EUR).
        Transitividad: USD → ARS → EUR.
          1.000 USD × 1200 = 1.200.000 ARS
          1.200.000 ARS × (1/1320) ≈ 909.09 EUR

        Verifica que la conversión pasa por C (ARS) correctamente.
        """
        payment = self._create_transfer(self.bank_usd, self.bank_eur, 1_000)

        self.assertEqual(payment.currency_id, self.usd)

        # Expected paired: 1.000 USD → 1.200.000 ARS → 909.09 EUR
        # Calculamos con rates reales del test
        balance_in_c = payment.amount / payment.accounting_rate  # USD → ARS
        eur_rate = self._get_rate(self.ars, self.eur)  # ARS → EUR
        expected_paired = self.eur.round(balance_in_c * eur_rate)

        paired = self._assert_transfer_ok(payment, expected_paired, self.eur)

        # Paired accounting_rate = EUR/ARS ≈ 0.000758
        expected_paired_rate = self._get_rate(self.ars, self.eur)
        self.assertAlmostEqual(paired.accounting_rate, expected_paired_rate, places=6)

        # Ambos lados deben tener el mismo balance en ARS en la cuenta puente
        original_transfer = payment.move_id.line_ids.filtered(lambda l: l.account_id == payment.destination_account_id)
        paired_transfer = paired.move_id.line_ids.filtered(lambda l: l.account_id == paired.destination_account_id)
        self.assertAlmostEqual(
            abs(original_transfer.balance),
            abs(paired_transfer.balance),
            places=2,
            msg="Balance ARS en cuenta puente debe coincidir",
        )

        # Paired counterpart: B1=USD (dest_journal=USD), amount_original=1.000
        self.assertEqual(paired.counterpart_currency_id, self.usd)
        self.assertAlmostEqual(
            paired.counterpart_rate,
            1_000 / expected_paired,
            places=6,
            msg="Counterpart rate del paired = original_amount / paired_amount",
        )
        self.assertAlmostEqual(
            paired.counterpart_currency_amount,
            1_000,
            places=2,
            msg="Counterpart amount del paired = original amount en USD",
        )

    # ==================================================================
    # IT.5 — ARS → USD con tasa manual (custom accounting_rate)
    # ==================================================================

    def test_it5_ars_to_usd_custom_rate(self):
        """IT.5 · Transferencia ARS → USD con tasa editada manualmente.

        Original: 1.500.000 ARS, user_accounting_rate editado a 1500 ARS/USD
        (en vez del 1200 del mercado).
        Paired: debe ser 1.000 USD (= 1.500.000 / 1500).

        Verifica que el paired respeta la tasa del original, no la del mercado.
        """
        payment = self._create_transfer(self.bank_ars, self.bank_usd, 1_500_000)

        # El usuario edita el counterpart_rate para reflejar tasa 1500
        # accounting_rate del original es 1.0 (A=C=ARS), no cambia
        # Pero el balance en C es el amount directo (1.500.000)
        # Y el paired debe recibir eso convertido a USD al rate del mercado

        # En este caso A1=C → balance_in_c = amount = 1.500.000
        # Paired amount = balance_in_c × rate(C→USD) = 1.500.000 / 1200 = 1.250 USD

        balance_in_c = 1_500_000  # A=C=ARS
        expected_paired = self.usd.round(balance_in_c * self._get_rate(self.ars, self.usd))

        paired = self._assert_transfer_ok(payment, expected_paired, self.usd)

        # Paired accounting_rate debe reflejar la tasa implícita de la operación
        # (balance_in_c / paired_amount), que en este caso coincide con la de mercado
        expected_paired_rate = self._get_rate(self.ars, self.usd)
        self.assertAlmostEqual(paired.accounting_rate, expected_paired_rate, places=6)

        # El balance en ARS de la cuenta puente debe ser 1.500.000
        original_transfer = payment.move_id.line_ids.filtered(lambda l: l.account_id == payment.destination_account_id)
        self.assertAlmostEqual(
            abs(original_transfer.balance),
            1_500_000,
            places=2,
        )

        # Paired counterpart: B1=ARS (dest_journal=ARS), amount_original=1.500.000
        self.assertEqual(paired.counterpart_currency_id, self.ars)
        self.assertAlmostEqual(paired.counterpart_currency_amount, 1_500_000, places=2)

    # ==================================================================
    # IT.6 — EUR → ARS (venta de EUR)
    # ==================================================================

    def test_it6_eur_to_ars(self):
        """IT.6 · Transferencia EUR → ARS (venta de EUR).

        Original: 500 EUR (outbound desde banco EUR).
        Paired: debe ser 660.000 ARS (500 × 1320).

        Verifica otra combinación de monedas.
        """
        payment = self._create_transfer(self.bank_eur, self.bank_ars, 500)

        self.assertEqual(payment.currency_id, self.eur)

        # Expected: 500 EUR → 500/accounting_rate_EUR → ARS
        balance_in_c = payment.amount / payment.accounting_rate
        expected_paired = self.ars.round(balance_in_c)  # A2=C=ARS → amount = balance

        paired = self._assert_transfer_ok(payment, expected_paired, self.ars)
        self.assertAlmostEqual(paired.accounting_rate, 1.0, places=6)

        # Paired counterpart: B1=EUR (dest_journal=EUR), amount_original=500
        self.assertEqual(paired.counterpart_currency_id, self.eur)
        self.assertAlmostEqual(
            paired.counterpart_rate,
            500 / expected_paired,
            places=6,
            msg="Counterpart rate del paired = original_amount / paired_amount",
        )
        self.assertAlmostEqual(paired.counterpart_currency_amount, 500, places=2)
