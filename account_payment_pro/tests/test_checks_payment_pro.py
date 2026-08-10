##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""account_payment_pro x check payments: several liquidity lines in one payment.

``_prepare_move_lines_per_type`` here rewrites the liquidity and counterpart
balances of every payment. Check payments are the only case where it receives
more than one liquidity line, so this is where the two features meet: the FX
rate, the write-off and the counterpart currency must all still add up when a
payment carries one line per check.

The suite that owns the check mechanics itself lives in
``l10n_latam_check_ux/tests``. Part of the harness of task 70884.
"""

from odoo import Command, fields
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestChecksPaymentPro(TestArCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.company = cls.company_ri
        cls.company.use_payment_pro = True
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))

        cls.ars = cls.company.currency_id
        cls.usd = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "USD")])
        cls.usd.active = True
        cls.env["res.currency.rate"].search(
            [("currency_id", "=", cls.usd.id), ("company_id", "=", cls.company.id)]
        ).unlink()
        cls.env["res.currency.rate"].create(
            [
                {
                    "name": cls.today,
                    "currency_id": cls.usd.id,
                    "company_id": cls.company.id,
                    "inverse_company_rate": 1200.0,
                },
                {
                    "name": fields.Date.add(cls.today, days=30),
                    "currency_id": cls.usd.id,
                    "company_id": cls.company.id,
                    "inverse_company_rate": 2400.0,
                },
            ]
        )

        cls.partner = cls.res_partner_adhoc
        cls.deferred_check_account = cls.env["account.account"].create(
            {
                "name": "Test Deferred Checks",
                "code": "TPPDEFCHK",
                "account_type": "asset_current",
                "reconcile": True,
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.write_off_account = cls.env["account.account"].create(
            {
                "name": "Test Write Off",
                "code": "TPPWO",
                "account_type": "expense",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "Test PPro Checks Bank", "code": "TPPB", "type": "bank", "company_id": cls.company.id}
        )
        cls.own_checks_line = cls.env["account.payment.method.line"].create(
            {
                "payment_method_id": cls.env.ref("l10n_latam_check.account_payment_method_own_checks").id,
                "name": "Own Checks",
                "payment_account_id": cls.deferred_check_account.id,
                "journal_id": cls.bank_journal.id,
            }
        )
        cls.write_off_type = cls.env["account.write_off.type"].create(
            {"name": "Test Write Off Type", "account_id": cls.write_off_account.id}
        )

    # ------------------------------------------------------------------
    def _own_check_payment(self, amounts, numbers, currency=None, check_dates=None, **kwargs):
        check_dates = check_dates or [self.today] * len(amounts)
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.partner.id,
            "journal_id": self.bank_journal.id,
            "company_id": self.company.id,
            "date": self.today,
            "currency_id": (currency or self.ars).id,
            "payment_method_line_id": self.own_checks_line.id,
            "l10n_latam_new_check_ids": [
                Command.create({"amount": amount, "payment_date": check_dates[i], "name": numbers[i]})
                for i, amount in enumerate(amounts)
            ],
        }
        vals.update(kwargs)
        return self.env["account.payment"].create(vals)

    def _liquidity_lines(self, payment):
        return payment.move_id.line_ids.filtered("l10n_latam_check_ids").sorted("id")

    def _counterpart_line(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in ("liability_payable", "asset_receivable")
        )

    def assert_balanced(self, payment):
        self.assertEqual(
            self.company.currency_id.round(sum(payment.move_id.line_ids.mapped("balance"))),
            0.0,
            "Entry %s is not balanced: %s"
            % (
                payment.move_id.name,
                [(line.name, line.amount_currency, line.balance) for line in payment.move_id.line_ids],
            ),
        )

    # ------------------------------------------------------------------
    # company currency
    # ------------------------------------------------------------------
    def test_multi_checks_company_currency(self):
        payment = self._own_check_payment([20, 30, 70], ["00030001", "00030002", "00030003"])
        payment.action_post()

        self.assert_balanced(payment)
        self.assertEqual(len(self._liquidity_lines(payment)), 3)
        self.assertEqual(sum(self._liquidity_lines(payment).mapped("balance")), -120)
        self.assertEqual(self._counterpart_line(payment).balance, 120)

    def test_multi_checks_with_write_off(self):
        """The write-off adds to the debt cancelled, not to the checks handed."""
        payment = self._own_check_payment(
            [40, 60],
            ["00030101", "00030102"],
            write_off_type_id=self.write_off_type.id,
            write_off_amount=5.0,
        )
        payment.action_post()

        self.assert_balanced(payment)
        self.assertEqual(sum(self._liquidity_lines(payment).mapped("balance")), -100, "Checks handed: 100")
        self.assertEqual(self._counterpart_line(payment).balance, 105, "Debt cancelled: 100 + 5 write-off")
        write_off_line = payment.move_id.line_ids.filtered(lambda line: line.account_id == self.write_off_account)
        self.assertEqual(write_off_line.balance, -5)

    def test_uneven_amounts_are_not_redistributed(self):
        payment = self._own_check_payment([33.33, 33.33, 33.34], ["00030201", "00030202", "00030203"])
        payment.action_post()

        self.assert_balanced(payment)
        self.assertEqual(sorted(abs(line.balance) for line in self._liquidity_lines(payment)), [33.33, 33.33, 33.34])

    # ------------------------------------------------------------------
    # foreign currency (A != C)
    # ------------------------------------------------------------------
    def test_multi_checks_foreign_currency_uses_accounting_rate(self):
        """La tasa del pago manda sobre *todas* las lineas de cheque, no solo
        sobre la primera - tanto la tasa de la tabla como una tipeada a mano."""
        payment = self._own_check_payment([20, 30, 70], ["00031001", "00031002", "00031003"], currency=self.usd)
        payment.action_post()

        self.assert_balanced(payment)
        lines = self._liquidity_lines(payment)
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(line.currency_id, self.usd, "The nominal stays in the check currency")
            self.assertEqual(
                abs(line.balance),
                self.company.currency_id.round(abs(line.amount_currency) / payment.accounting_rate),
                "Every check line converts with the payment accounting rate",
            )
        self.assertEqual(abs(sum(lines.mapped("amount_currency"))), 120)
        self.assertEqual(abs(sum(lines.mapped("balance"))), 144000, "120 USD at 1200 ARS")

        counterpart = self._counterpart_line(payment)
        self.assertEqual(len(counterpart), 1, "One counterpart line regardless of the number of checks")
        self.assertEqual(abs(counterpart.balance), abs(sum(lines.mapped("balance"))))

        manual = self._own_check_payment([20, 30, 70], ["00031101", "00031102", "00031103"], currency=self.usd)
        manual.accounting_rate = 1 / 1000.0
        manual.action_post()

        self.assert_balanced(manual)
        self.assertEqual(abs(sum(self._liquidity_lines(manual).mapped("balance"))), 120000, "120 USD at 1000 ARS")
        for line in self._liquidity_lines(manual):
            self.assertEqual(abs(line.balance), abs(line.amount_currency) * 1000)

    def test_multi_checks_with_a_rate_that_does_not_divide_exactly(self):
        """Ticket 123832: dos cheques y una tasa cuya división deja fracciones de
        centavo. Cada cifra del asiento se redondea por separado, así que el balance
        de la contrapartida y su nominal tienen que derivar de los balances ya
        redondeados de las líneas de cheque; si alguno se calcula solo, ``action_post``
        explota con "El asiento no está balanceado".
        """
        rate = 0.024841017488076312  # 1 USD = 40,256; la division no da exacta
        payment = self._own_check_payment([39717.71, 39717.71], ["00031301", "00031302"], currency=self.usd)
        payment.accounting_rate = rate
        payment.action_post()

        self.assert_balanced(payment)
        lines = self._liquidity_lines(payment)
        self.assertEqual(
            [abs(line.balance) for line in lines],
            [1598876.13, 1598876.13],
            "Cheques iguales tienen que valer lo mismo: cada uno es su propia conversión",
        )
        self.assertEqual(len(payment.move_id.line_ids), 3, "Sin líneas de ajuste extra en el asiento")
        counterpart = self._counterpart_line(payment)
        self.assertEqual(
            abs(counterpart.balance),
            3197752.26,
            "La contrapartida absorbe el residuo: es la suma de las conversiones de cada cheque",
        )
        self.assertEqual(
            abs(counterpart.amount_currency),
            abs(counterpart.balance),
            "En moneda de compañía el nominal y el balance son la misma cifra",
        )

        # Misma operación con la contrapartida en la moneda del pago en vez de la de
        # compañía: el otro camino por el que se desbalanceaba (B1 == A, counterpart_rate 1).
        in_payment_currency = self._own_check_payment([39717.71, 39717.71], ["00031303", "00031304"], currency=self.usd)
        in_payment_currency.counterpart_currency_id = self.usd
        in_payment_currency.accounting_rate = rate
        in_payment_currency.action_post()

        self.assert_balanced(in_payment_currency)
        counterpart = self._counterpart_line(in_payment_currency)
        self.assertEqual(counterpart.currency_id, self.usd)
        self.assertEqual(
            abs(counterpart.balance),
            3197752.26,
            "También acá la contrapartida es la suma de las conversiones de cada cheque",
        )
        self.assertEqual(abs(counterpart.amount_currency), 79435.42)
        self.assertEqual(
            [abs(line.balance) for line in self._liquidity_lines(in_payment_currency)],
            [1598876.13, 1598876.13],
            "Cheques iguales, valores iguales, sea cual sea la moneda de la contrapartida",
        )

    def test_single_check_derives_its_balance_from_amount_exact(self):
        """Con una sola línea de liquidez el balance deriva de ``amount_exact``, no del
        nominal redondeado a la moneda del cheque."""
        payment = self._own_check_payment([1000.02], ["00031401"], currency=self.usd)
        payment.accounting_rate = 1 / 1247.35
        payment.amount_exact = 1000.0234567
        payment.action_post()

        self.assert_balanced(payment)
        line = self._liquidity_lines(payment)
        self.assertEqual(len(line), 1)
        self.assertEqual(abs(line.amount_currency), 1000.02, "El nominal se redondea a la moneda del cheque")
        self.assertEqual(
            abs(line.balance),
            self.company.currency_id.round(1000.0234567 * 1247.35),
            "El balance sale de amount_exact, no del nominal redondeado",
        )

    def test_deferred_checks_in_foreign_currency_stay_balanced(self):
        """Deferred checks (payment_date well after the payment date).

        The rate moves between both dates; the entry must still balance and every
        line must be converted at the payment date. NOTE: with payment_pro
        disabled this very case fails today (BUG-2 of task 70884), because the
        patch converts each check at its own date while the counterpart keeps the
        payment date; payment_pro recomputes both and hides it.
        """
        payment = self._own_check_payment(
            [20, 30, 70],
            ["00031201", "00031202", "00031203"],
            currency=self.usd,
            check_dates=[fields.Date.add(self.today, days=40)] * 3,
        )
        payment.action_post()

        self.assert_balanced(payment)
        self.assertEqual(
            abs(sum(self._liquidity_lines(payment).mapped("balance"))),
            144000,
            "Conversion must use the payment date rate (1200), not the check date one (2400)",
        )

    # ------------------------------------------------------------------
    # synchronization
    # ------------------------------------------------------------------
    def test_amount_can_be_written_on_a_multi_check_payment_with_a_draft_move(self):
        """Base Odoo blocks writing ``amount`` when a payment has several
        liquidity lines. Check payments legitimately have several, so the block
        must not apply to them: this is the single core behaviour a relocation of
        the patch has to reproduce.

        The payment is reset to draft on purpose: ``_synchronize_to_moves``
        returns early when the move is already posted, so writing on a posted
        payment would never reach the guard and the test would pass for the
        wrong reason.
        """
        payment = self._own_check_payment([20, 30, 70], ["00032001", "00032002", "00032003"])
        payment.action_post()
        payment.action_draft()
        self.assertEqual(payment.move_id.state, "draft")
        self.assertEqual(len(self._liquidity_lines(payment)), 3, "The draft move keeps one line per check")

        payment.write({"amount": 120})

        self.assert_balanced(payment)
        self.assertEqual(len(self._liquidity_lines(payment)), 3, "The check lines must survive the sync")
        self.assertEqual(len(payment.move_id.line_ids), 4)

        payment.action_post()
        self.assert_balanced(payment)
        self.assertEqual(len(self._liquidity_lines(payment)), 3, "Reposting keeps one line per check")
        self.assertEqual(len(payment.move_id.line_ids), 4)

    # def test_writing_amount_on_two_payments_at_once_crashes_today(self):
    #     """EQUIVALENCE (task 70884, BUG-3).
    #
    #     Pins what the patched core does today: it classifies the new lines with
    #     ``self.outstanding_account_id`` instead of ``pay.outstanding_account_id``
    #     inside its own ``for pay in self`` loop, so writing a trigger field on
    #     several payments whose moves are in draft and whose outstanding accounts
    #     differ raises ``Expected singleton``. It is not check specific: any
    #     payment reset to draft is affected.
    #
    #     Whether the relocation reproduces it depends on how
    #     ``_synchronize_to_moves`` is ported: copying the patched method verbatim
    #     keeps the crash, delegating to ``super()`` fixes it - and then this
    #     assertion has to be inverted in that same PR.
    #     """
    #     other_account = self.env["account.account"].create(
    #         {
    #             "name": "Test Deferred Checks 2",
    #             "code": "TPPDEFCHK2",
    #             "account_type": "asset_current",
    #             "reconcile": True,
    #             "company_ids": [Command.set(self.company.ids)],
    #         }
    #     )
    #     other_line = self.env["account.payment.method.line"].create(
    #         {
    #             "payment_method_id": self.own_checks_line.payment_method_id.id,
    #             "name": "Own Checks 2",
    #             "payment_account_id": other_account.id,
    #             "journal_id": self.bank_journal.id,
    #         }
    #     )
    #     first = self._own_check_payment([20, 30], ["00032301", "00032302"])
    #     second = self._own_check_payment([20, 30], ["00032303", "00032304"])
    #     second.payment_method_line_id = other_line
    #     payments = first + second
    #     payments.action_post()
    #     payments.action_draft()
    #     self.assertNotEqual(first.outstanding_account_id, second.outstanding_account_id)
    #
    #     with self.assertRaisesRegex(ValueError, "Expected singleton"):
    #         payments.write({"amount": 50})
