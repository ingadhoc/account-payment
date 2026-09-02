from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestOwnCheckCurrency(AccountInvariantsMixin, TransactionCase):
    """Cheque propio emitido en la misma moneda que la factura que paga.

    FCP-R08-E4: cruce de moneda del cheque, del asiento y del débito. Lo que
    este test cubre es la parte de "el cheque queda en USD": pagar una deuda
    en moneda extranjera con un cheque propio en esa misma moneda no dispara
    ninguna diferencia de cambio prematura — la deuda y el cheque son la
    misma moneda, así que no hay conversión que hacer todavía.

    La segunda mitad del escenario ("el débito posterior no arrastra la
    conversión al TC del día") queda fuera de este módulo: el botón de débito
    y su wizard viven en ``l10n_latam_check_ux``, que ``account_payment_pro``
    no declara como dependencia (igual que el corte documentado en
    ``reference_runbot_modified_modules_dependency_scope``, y el mismo límite
    que ``l10n_ar_tax:TestPaymentChecksWithholding`` documenta para FCP-R10).
    Queda cubierta por composición: el débito solo reconcilia la línea de
    liquidez propia del cheque por su nominal — no vuelve a convertir nada
    (``l10n_latam_check_ux:test_debit_one_check_of_many``) — y esa línea, acá,
    ya está probada en la moneda del cheque, sin diferencia de cambio.
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

        cls.vendor = cls.env["res.partner"].create({"name": "Test Own Check Currency Vendor"})
        cls.expense_account = cls.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "=", cls.company.id)], limit=1
        )
        cls.deferred_check_account = cls.env["account.account"].create(
            {
                "name": "Test Own Check Currency Deferred",
                "code": "TOCCDEF",
                "account_type": "asset_current",
                "reconcile": True,
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "Test Own Check Currency Bank", "type": "bank", "code": "TOCCB", "company_id": cls.company.id}
        )
        cls.own_checks_line = cls.env["account.payment.method.line"].create(
            {
                "payment_method_id": cls.env.ref("l10n_latam_check.account_payment_method_own_checks").id,
                "name": "Own Checks",
                "payment_account_id": cls.deferred_check_account.id,
                "journal_id": cls.bank_journal.id,
            }
        )

    def _make_bill(self, amount):
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
                            "name": "Test own check currency line",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": self.expense_account.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _fx_lines(self, payment):
        fx_accounts = (
            self.company.income_currency_exchange_account_id | self.company.expense_currency_exchange_account_id
        )
        return payment.exchange_diff_move_ids.line_ids.filtered(lambda line: line.account_id in fx_accounts)

    def test_a_check_in_the_same_currency_as_the_bill_books_no_exchange_difference(self):
        """Dada una factura en USD 1.000, cuando se paga con un cheque propio
        de USD 1.000 (misma moneda), entonces la factura queda saldada, el
        cheque conserva su nominal en USD, y no se generó ninguna diferencia
        de cambio: no hubo conversión, porque la deuda y el cheque nunca
        estuvieron en monedas distintas.

        Cubre FCP-R08-E4 (parcial: ver docstring de la clase).
        """
        bill = self._make_bill(1000.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.vendor.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "date": "2026-01-01",
                "currency_id": self.usd.id,
                "payment_method_line_id": self.own_checks_line.id,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
                "l10n_latam_new_check_ids": [
                    Command.create({"name": "00000410", "payment_date": "2026-01-01", "amount": 1000.0})
                ],
            }
        )
        payment.action_post()
        self.assert_payment_invariants(payment, "cheque propio en la misma moneda que la factura")

        with self.subTest("la factura queda saldada (en proceso de pago hasta que se debite el cheque)"):
            self.assertEqual(bill.payment_state, "in_payment")
            self.assertEqual(bill.amount_residual, 0.0)
        with self.subTest("el cheque conserva su nominal en USD"):
            check_line = payment.move_id.line_ids.filtered("l10n_latam_check_ids")
            self.assertEqual(check_line.currency_id, self.usd)
            self.assertEqual(abs(check_line.amount_currency), 1000.0)
        with self.subTest("no se generó ninguna diferencia de cambio"):
            self.assertFalse(payment.exchange_diff_move_ids)
            self.assertFalse(self._fx_lines(payment))
