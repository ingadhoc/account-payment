from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestResetAndRecomputeRate(TransactionCase):
    """Pago en moneda extranjera vuelto a borrador y re-confirmado a otra fecha
    (otro TC): la diferencia de cambio anterior se revierte y se recalcula al
    TC nuevo, sin quedar las dos.

    Cubre FCP-R08-E8 / FCP-R09-E6 (mismo mecanismo, dos IDs de escenario porque
    la spec lo lista en ambos casos).

    FCP-R06-E7 (factura USD con diferencia de cambio, transitoria conciliada)
    está en ``test_payment_state.py`` — es un escenario de estado de pago, no
    de reset, y ese archivo ya concilia la transitoria con un
    ``account.move`` genérico (sin pasar por ``account.bank.statement.line``
    ni por el render de reporte que dispara).
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
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-03-01", "rate": 1.0 / 1200.0}
        )

        cls.vendor = cls.env["res.partner"].create({"name": "Test Reset Recompute Rate Vendor"})
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )

    def _fx_lines(self, payment):
        """Líneas de diferencia de cambio: no se identifican por un
        ``account_type`` fijo (varía según el plan de cuentas de la
        compañía), sino por ser las cuentas de ganancia/pérdida por cambio
        configuradas en la propia compañía."""
        fx_accounts = (
            self.company.income_currency_exchange_account_id | self.company.expense_currency_exchange_account_id
        )
        return payment.exchange_diff_move_ids.line_ids.filtered(lambda line: line.account_id in fx_accounts)

    def test_reset_and_reconfirm_at_a_new_rate_recalculates_without_duplicating_the_difference(self):
        """Factura USD 1.000 al TC 1.000, pagada al TC 1.100 (diferencia
        $100.000), vuelta a borrador y re-confirmada al TC 1.200 (fecha
        posterior): la diferencia se recalcula a $200.000 — la del TC 1.100 no
        queda pegada ni se duplica.
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
                            "name": "Test reset recompute rate line",
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
        payment.amount = 1000.0
        payment.action_post()

        first_fx_lines = self._fx_lines(payment)
        self.assertEqual(first_fx_lines.balance, 100000.0, "diferencia al TC 1.100")

        payment.action_draft()
        payment.date = "2026-03-01"
        payment.action_post()

        with self.subTest("una sola diferencia de cambio, recalculada al TC nuevo"):
            self.assertEqual(len(payment.exchange_diff_move_ids), 1)
            new_fx_lines = self._fx_lines(payment)
            self.assertEqual(new_fx_lines.balance, 200000.0, "diferencia al TC nuevo (1.200), no la vieja pegada")

        with self.subTest("la factura sigue saldada en ambas monedas"):
            self.assertEqual(bill.amount_residual, 0.0)
            self.assertEqual(self.company.currency_id.round(sum(bill.line_ids.mapped("amount_residual"))), 0.0)
