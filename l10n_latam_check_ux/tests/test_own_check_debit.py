##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests.common import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestOwnCheckDebit(LatamCheckCommon):
    """Débito de cheques propios y conciliación de la OP contra el banco.

    FCP-R13: al conciliar el movimiento bancario del débito de un cheque no
    aparecían las líneas de los cheques de la OP, o bajaba un cheque que no era
    el debitado. FCP-R10-E7: revertido el débito, el cheque tiene que volver a
    emitido y la cuenta de cheques a pagar recuperar el importe.

    Lo que expone el cruce es que los cheques de una misma OP comparten importe
    y fecha: si el débito eligiera "el que aparece" en vez del apunte del cheque,
    los tests de importes iguales pasarían igual y los de orden inverso no.

    Cubre FCP-R10-E7 y FCP-R13-E1/E2/E3/E6.
    Tickets 118050, 120290, 120581, 114272, 122219, 118579, 119844.
    """

    def _issue_checks(self, amounts, numbers, check_dates=None):
        """OP de cheques propios confirmada y conciliada contra su deuda."""
        payment = self._create_own_check_payment(amounts, numbers=numbers, check_dates=check_dates)
        debt_line = self._create_debt_move(sum(amounts), account=payment.destination_account_id)
        payment.action_post()
        (self._counterpart_lines(payment) + debt_line).reconcile()
        self.assert_check_lines_match(payment)
        return payment

    def _debit(self, check, date=None):
        self.env["account.check.action.wizard"].with_context(
            active_model="l10n_latam.check", active_ids=check.ids
        ).create({"date": date or self.today}).action_confirm()
        check.invalidate_recordset()

    def _open_check_lines(self):
        """Apuntes de cheques a pagar todavía sin cancelar: es lo que el usuario
        ve como pendiente de conciliar contra el banco."""
        return self.env["account.move.line"].search(
            [
                ("account_id", "=", self.deferred_check_account.id),
                ("company_id", "=", self.company.id),
                ("parent_state", "=", "posted"),
                ("amount_residual", "!=", 0.0),
            ]
        )

    def _account_balance(self):
        lines = self.env["account.move.line"].search(
            [
                ("account_id", "=", self.deferred_check_account.id),
                ("company_id", "=", self.company.id),
                ("parent_state", "=", "posted"),
            ]
        )
        return self.company_currency.round(sum(lines.mapped("balance")))

    def test_debiting_one_of_three_equal_checks_only_touches_that_one(self):
        """Dada una OP con tres cheques propios de $30.000 cada uno, cuando se
        debita el 0002, entonces se canceló el apunte del 0002 y solo ese: el
        0002 queda debitado, el 0001 y el 0003 siguen emitidos y sin conciliar, y
        la cuenta de cheques a pagar bajó exactamente $30.000.

        Cubre FCP-R13-E1.
        """
        payment = self._issue_checks([30000.0, 30000.0, 30000.0], numbers=["0001", "0002", "0003"])
        checks = payment.l10n_latam_new_check_ids
        by_number = {check.name: check for check in checks}
        balance_before = self._account_balance()

        with self.subTest("los tres cheques están disponibles para conciliar, identificables por número"):
            open_lines = self._open_check_lines()
            self.assertEqual(len(open_lines), 3)
            self.assertEqual(open_lines.l10n_latam_check_ids, checks)
            # El mismo importe en los tres es justo lo que hace que el usuario no
            # pueda distinguirlos si el número no viaja en el apunte.
            self.assertEqual(sorted(open_lines.l10n_latam_check_ids.mapped("name")), ["0001", "0002", "0003"])

        self._debit(by_number["0002"])

        with self.subTest("el cheque debitado es el 0002 y ninguno más"):
            self.assertEqual(by_number["0002"].issue_state, "debited")
            self.assertEqual(by_number["0001"].issue_state, "handed")
            self.assertEqual(by_number["0003"].issue_state, "handed")
        with self.subTest("se canceló el apunte del 0002, no el de otro cheque"):
            self.assertEqual(by_number["0002"].outstanding_line_id.amount_residual, 0.0)
            self.assertEqual(by_number["0001"].outstanding_line_id.amount_residual, -30000.0)
            self.assertEqual(by_number["0003"].outstanding_line_id.amount_residual, -30000.0)
        with self.subTest("la cuenta de cheques a pagar bajó exactamente el importe del cheque"):
            self.assertEqual(self._account_balance() - balance_before, 30000.0)

    def test_checks_of_different_amounts_are_debited_each_for_its_own(self):
        """Dada una OP con cheques de $20.000, $30.000 y $40.000, cuando se
        debita cada uno, entonces cada débito mueve su propio importe y ninguno
        arrastra el de otro.

        Cubre FCP-R13-E2.
        """
        payment = self._issue_checks([20000.0, 30000.0, 40000.0], numbers=["0011", "0012", "0013"])
        by_number = {check.name: check for check in payment.l10n_latam_new_check_ids}

        for number, amount in (("0012", 30000.0), ("0011", 20000.0), ("0013", 40000.0)):
            balance_before = self._account_balance()
            self._debit(by_number[number])
            with self.subTest("el débito del cheque %s mueve sus $%s" % (number, amount)):
                self.assertEqual(self._account_balance() - balance_before, amount)
                self.assertEqual(by_number[number].issue_state, "debited")

        with self.subTest("debitados los tres, no queda nada abierto en cheques a pagar"):
            self.assertFalse(self._open_check_lines())

    def test_debiting_in_reverse_order_does_not_swap_the_checks(self):
        """Dada una OP con tres cheques del mismo importe y la misma fecha de
        pago, cuando se debitan en orden inverso (0003, 0002, 0001), entonces
        cada débito cancela el apunte de su propio cheque: el orden no reasigna
        los cheques entre sí.

        Cubre FCP-R13-E3 (CHK-025, apuntes cruzados).
        """
        payment = self._issue_checks(
            [15000.0, 15000.0, 15000.0], numbers=["0021", "0022", "0023"], check_dates=[self.today] * 3
        )
        by_number = {check.name: check for check in payment.l10n_latam_new_check_ids}
        lines_before = {number: check.outstanding_line_id for number, check in by_number.items()}

        for number in ("0023", "0022", "0021"):
            self._debit(by_number[number])
            with self.subTest("el débito del %s cancela su propio apunte" % number):
                self.assertEqual(by_number[number].outstanding_line_id, lines_before[number])
                self.assertEqual(by_number[number].outstanding_line_id.amount_residual, 0.0)
                self.assertEqual(by_number[number].issue_state, "debited")
            # Se debita de mayor a menor: los de número menor todavía no se tocaron.
            for pending in [n for n in ("0021", "0022", "0023") if n < number]:
                with self.subTest("el %s todavía no se tocó" % pending):
                    self.assertEqual(by_number[pending].issue_state, "handed")
                    self.assertEqual(by_number[pending].outstanding_line_id.amount_residual, -15000.0)

        with self.subTest("cada cheque conserva el apunte con el que nació"):
            for number, line in lines_before.items():
                self.assertEqual(by_number[number].outstanding_line_id, line)

    def test_a_reverted_debit_puts_the_check_back_as_handed(self):
        """Dado un cheque propio debitado, cuando se revierte el asiento del
        débito y se desconcilia, entonces el cheque vuelve a emitido, la cuenta
        de cheques a pagar recupera el importe y no queda ningún asiento
        huérfano: el de reversión cierra contra el del débito.

        Cubre FCP-R10-E7 (CHK-021/022).
        """
        payment = self._issue_checks([25000.0], numbers=["0031"])
        check = payment.l10n_latam_new_check_ids
        balance_issued = self._account_balance()
        self._debit(check)
        self.assertEqual(check.issue_state, "debited")

        debit_line = (check.outstanding_line_id.matched_debit_ids.debit_move_id).filtered(
            lambda line: line.account_id == self.deferred_check_account
        )
        debit_move = debit_line.move_id
        check.outstanding_line_id.remove_move_reconcile()
        reversal = debit_move._reverse_moves(cancel=True)

        check.invalidate_recordset()
        with self.subTest("el cheque vuelve a emitido, no queda debitado"):
            self.assertEqual(check.issue_state, "handed")
        with self.subTest("la cuenta de cheques a pagar vuelve al saldo de la emisión"):
            self.assertEqual(self._account_balance(), balance_issued)
        with self.subTest("el débito y su reversión quedan cerrados entre sí, sin asientos sueltos"):
            self.assertEqual(reversal.state, "posted")
            self.assertEqual(debit_line.amount_residual, 0.0)
        with self.subTest("el apunte del cheque vuelve a estar disponible para conciliar"):
            self.assertIn(check.outstanding_line_id, self._open_check_lines())

    def test_partially_debited_orders_do_not_mix_their_checks(self):
        """Dadas dos OP con cheques del mismo importe, una con su primer cheque
        ya debitado, cuando se mira lo que queda por conciliar, entonces
        aparecen solo los cheques no debitados y cada uno sigue colgado de su
        propia OP: el estado mixto entre dos órdenes no los mezcla.

        Cubre FCP-R13-E6.
        """
        first = self._issue_checks([10000.0, 10000.0, 10000.0], numbers=["0041", "0042", "0043"])
        second = self._issue_checks([10000.0, 10000.0], numbers=["0051", "0052"])
        first_checks = {check.name: check for check in first.l10n_latam_new_check_ids}

        self._debit(first_checks["0041"])

        open_lines = self._open_check_lines()
        with self.subTest("el debitado desaparece de lo conciliable; los otros cuatro siguen"):
            self.assertEqual(sorted(open_lines.l10n_latam_check_ids.mapped("name")), ["0042", "0043", "0051", "0052"])
        with self.subTest("cada cheque pendiente sigue colgado de su propia OP"):
            for check in open_lines.l10n_latam_check_ids:
                expected = first if check.name.startswith("004") else second
                self.assertEqual(check.payment_id, expected)
        with self.subTest("el importe pendiente de cada OP es el de sus cheques no debitados"):
            first_open = open_lines.filtered(lambda line: line.l10n_latam_check_ids.payment_id == first)
            second_open = open_lines.filtered(lambda line: line.l10n_latam_check_ids.payment_id == second)
            self.assertEqual(sum(first_open.mapped("amount_residual")), -20000.0)
            self.assertEqual(sum(second_open.mapped("amount_residual")), -20000.0)
