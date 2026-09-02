from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPaymentState(AccountInvariantsMixin, TransactionCase):
    """El estado de pago de la factura es uno solo y explícito en cada etapa.

    FCP-R06: la factura totalmente conciliada con su cobro seguía figurando "en
    proceso de pago" en vez de "pagada", y el cliente veía deuda que no existe.
    El caso vale tanto por los estados que verifica como por la regla que impone:
    ninguna verificación acepta "pagada o en proceso" indistintamente.

    Cubre FCP-R06-E2/E4/E5/E6 (E1 es el circuito completo, que sirve de base a
    todos).
    Tickets 118389, 118707, 119616, 120143, 122088, 123368, 123602, 121325,
    119561, 120900, 122740.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.misc_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "general")], limit=1
        )
        cls.product = cls.env.ref("product.product_product_16")
        cls.customer = cls.env["res.partner"].create({"name": "Test Payment State Customer"})

        # Configuración del escenario: dos diarios de banco que solo difieren en
        # la cuenta transitoria. Es la diferencia que decide si la factura pasa
        # por "en proceso de pago" o queda pagada de una, así que el test la crea
        # en vez de depender de cómo esté configurada la base.
        cls.bank_with_outstanding = cls.env["account.journal"].create(
            {"name": "Test Payment State Bank", "type": "bank", "code": "TPSB", "company_id": cls.company.id}
        )
        cls.outstanding_account = cls.env["account.account"].create(
            {
                "name": "Test Payment State Outstanding Receipts",
                "code": "TPSOUT",
                "account_type": "asset_current",
                "reconcile": True,
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.bank_with_outstanding.inbound_payment_method_line_ids.payment_account_id = cls.outstanding_account

        cls.bank_direct = cls.env["account.journal"].create(
            {"name": "Test Payment State Direct Bank", "type": "bank", "code": "TPSD", "company_id": cls.company.id}
        )
        cls.bank_direct.inbound_payment_method_line_ids.payment_account_id = cls.bank_direct.default_account_id

        # moneda extranjera, para el cobro con diferencia de cambio + transitoria (E7)
        cls.usd = cls.env.ref("base.EUR")
        if cls.usd == cls.company.currency_id:
            cls.usd = cls.env.ref("base.USD")
        cls.usd.active = True
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-01-01", "rate": 0.001}
        )
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-01-05", "rate": 1.0 / 1100.0}
        )

    def _make_invoice(self, amount=10000.0):
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.customer.id,
                "invoice_date": "2026-01-01",
                "move_type": "out_invoice",
                "journal_id": self.sale_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1, "price_unit": amount})
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _make_payment(self, invoice, amount, journal):
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": journal.id,
                "partner_id": self.customer.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "date": "2026-01-01",
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        payment.amount = amount
        payment.action_post()
        self.assert_payment_invariants(payment, "cobro %s" % invoice.name)
        return payment

    def _outstanding_line(self, payment):
        return payment.move_id.line_ids.filtered(lambda line: line.account_id == self.outstanding_account)

    def _settle_outstanding(self, payment):
        """Cierra el circuito: la transitoria se concilia contra el banco, que es
        lo que en la operación real hace la conciliación del extracto."""
        outstanding_line = self._outstanding_line(payment)
        bank_entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": "2026-01-05",
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Extracto bancario",
                            "account_id": self.bank_with_outstanding.default_account_id.id,
                            "debit": outstanding_line.debit,
                            "credit": 0.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Cancela la transitoria",
                            "account_id": self.outstanding_account.id,
                            "debit": 0.0,
                            "credit": outstanding_line.debit,
                        }
                    ),
                ],
            }
        )
        bank_entry.action_post()
        counterpart = bank_entry.line_ids.filtered(lambda line: line.account_id == self.outstanding_account)
        (outstanding_line + counterpart).reconcile()
        return counterpart

    def test_a_journal_without_an_outstanding_account_leaves_the_invoice_paid_at_once(self):
        """Dada una factura de $10.000 cobrada por un diario que asienta directo
        en la cuenta de banco, cuando se confirma el cobro, entonces la factura
        queda pagada sin pasar por "en proceso de pago": no hay circuito
        pendiente que cerrar.

        Cubre FCP-R06-E2.
        """
        invoice = self._make_invoice()
        self._make_payment(invoice, 10000.0, self.bank_direct)

        with self.subTest("pagada de una, sin etapa intermedia"):
            self.assertEqual(invoice.payment_state, "paid")
            self.assertEqual(invoice.amount_residual, 0.0)

    def test_the_invoice_is_in_payment_until_the_outstanding_account_is_reconciled(self):
        """Dada una factura de $10.000 cobrada por un diario con cuenta
        transitoria, cuando el cobro se confirma pero la transitoria sigue
        abierta, entonces la factura está "en proceso de pago" con saldo $0; y
        cuando la transitoria se concilia contra el banco, entonces pasa a
        "pagada". El saldo es $0 en las dos etapas: lo que las distingue es el
        estado, no el importe.

        Cubre FCP-R06-E1 (base del caso).
        """
        invoice = self._make_invoice()
        payment = self._make_payment(invoice, 10000.0, self.bank_with_outstanding)

        with self.subTest("transitoria abierta: en proceso de pago, nunca pagada"):
            self.assertEqual(invoice.payment_state, "in_payment")
            self.assertEqual(invoice.amount_residual, 0.0)

        self._settle_outstanding(payment)

        with self.subTest("circuito cerrado: pagada, nunca en proceso"):
            self.assertEqual(invoice.payment_state, "paid")
            self.assertEqual(invoice.amount_residual, 0.0)

    def test_a_partial_collection_is_partial_and_not_one_of_the_other_two_states(self):
        """Dada una factura de $10.000, cuando se cobran $4.000 y la transitoria
        de ese cobro se concilia, entonces la factura queda en pago parcial con
        saldo $6.000 — ni pagada ni en proceso de pago, que son los dos estados
        con los que se confunde.

        Cubre FCP-R06-E4.
        """
        invoice = self._make_invoice()
        payment = self._make_payment(invoice, 4000.0, self.bank_with_outstanding)
        self._settle_outstanding(payment)

        with self.subTest("pago parcial, con el saldo abierto por la diferencia"):
            self.assertEqual(invoice.payment_state, "partial")
            self.assertEqual(invoice.amount_residual, 6000.0)

    def test_unreconciling_the_outstanding_account_sends_the_invoice_back_to_in_payment(self):
        """Dada una factura ya pagada con su transitoria conciliada, cuando se
        desconcilia la transitoria, entonces la factura vuelve a "en proceso de
        pago" — no a "no pagada" (el cobro sigue existiendo) ni se queda pegada
        en "pagada".

        Cubre FCP-R06-E5.
        """
        invoice = self._make_invoice()
        payment = self._make_payment(invoice, 10000.0, self.bank_with_outstanding)
        counterpart = self._settle_outstanding(payment)
        self.assertEqual(invoice.payment_state, "paid")

        (self._outstanding_line(payment) + counterpart).remove_move_reconcile()

        with self.subTest("vuelve a en proceso de pago, con el saldo todavía en $0"):
            self.assertEqual(invoice.payment_state, "in_payment")
            self.assertEqual(invoice.amount_residual, 0.0)

    def test_two_partial_collections_stay_in_payment_until_every_outstanding_closes(self):
        """Dada una factura de $10.000 cobrada con dos pagos parciales de $5.000,
        cuando se concilia la transitoria de uno solo, entonces la factura sigue
        "en proceso de pago" aunque su saldo ya sea $0; y solo cuando cierra
        también la del segundo pasa a "pagada". El estado mixto es el que se
        escapaba: alcanza con que una transitoria quede abierta.

        Cubre FCP-R06-E6.
        """
        invoice = self._make_invoice()
        first = self._make_payment(invoice, 5000.0, self.bank_with_outstanding)
        second = self._make_payment(invoice, 5000.0, self.bank_with_outstanding)

        with self.subTest("cobrada del todo pero con las dos transitorias abiertas"):
            self.assertEqual(invoice.amount_residual, 0.0)
            self.assertEqual(invoice.payment_state, "in_payment")

        self._settle_outstanding(first)
        with self.subTest("una transitoria cerrada y la otra abierta: sigue en proceso"):
            self.assertEqual(invoice.payment_state, "in_payment")

        self._settle_outstanding(second)
        with self.subTest("cerradas las dos: recién ahí queda pagada"):
            self.assertEqual(invoice.payment_state, "paid")

    def test_a_foreign_currency_collection_with_exchange_difference_settles_to_paid(self):
        """Dada una factura USD 1.000 al TC 1.000, cobrada al TC 1.100 (con
        diferencia de cambio) por un diario con transitoria, cuando se concilia
        esa transitoria, entonces la factura pasa a "pagada" con saldo $0 en
        las dos monedas — el residuo de redondeo por conversión de moneda no
        la deja pegada en "en proceso de pago".

        Cubre FCP-R06-E7.
        """
        income = self.env["account.account"].search(
            [("account_type", "=", "income"), ("company_ids", "=", self.company.id)], limit=1
        )
        invoice = self.env["account.move"].create(
            {
                "partner_id": self.customer.id,
                "invoice_date": "2026-01-01",
                "move_type": "out_invoice",
                "journal_id": self.sale_journal.id,
                "company_id": self.company.id,
                "currency_id": self.usd.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test payment state USD line",
                            "quantity": 1,
                            "price_unit": 1000.0,
                            "account_id": income.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        debt = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_with_outstanding.id,
                "partner_id": self.customer.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "date": "2026-01-05",
                "currency_id": self.usd.id,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        payment.amount = 1000.0
        payment.action_post()
        self.assert_payment_invariants(payment, "cobro con diferencia de cambio")

        with self.subTest("transitoria abierta: en proceso de pago, saldo 0 en ambas monedas"):
            self.assertEqual(invoice.payment_state, "in_payment")
            self.assertEqual(invoice.amount_residual, 0.0)
            self.assertEqual(invoice.amount_residual_signed, 0.0)

        self._settle_outstanding(payment)

        with self.subTest("transitoria conciliada: pagada, sin residuo por la diferencia de cambio"):
            self.assertEqual(invoice.payment_state, "paid")
            self.assertEqual(invoice.amount_residual, 0.0)
            self.assertEqual(invoice.amount_residual_signed, 0.0)
