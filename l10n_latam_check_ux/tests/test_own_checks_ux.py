##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Own checks: journal entry shape, lifecycle and border cases.

Part of the harness of task 70884: it pins the behaviour of the core check patch
the ADHOC image carries, now relocated into our modules.

Tests whose name ends in ``_today`` pin a side effect of the patch on purpose -
they are not the desired behaviour, and the task documents each one. They assert
the relocation is equivalent; fixing any of them is a separate PR, which is where
the assertion flips.
"""

from unittest.mock import patch

from odoo import Command, fields
from odoo.addons.l10n_latam_check.models.account_payment import AccountPayment as CoreCheckPayment
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestOwnChecksEntry(LatamCheckCommon):
    """The journal entry generated when issuing own checks."""

    def test_multi_check_entry_shape(self):
        """3 cheques diferidos con montos que no dividen parejo: una linea de
        liquidez por cheque dentro del asiento del pago (con su nominal, su
        vencimiento, su numero y su cuenta, ver ``assert_check_lines_match``),
        una sola contrapartida y ningun asiento extra."""
        dates = [fields.Date.add(self.today, days=days) for days in (10, 20, 30)]
        payment = self._create_own_check_payment(
            [33.33, 33.33, 33.34], numbers=["00000201", "00000202", "00000203"], check_dates=dates
        )
        payment.action_post()

        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
        lines = self._check_lines(payment)
        self.assertEqual(payment.amount, 100)
        self.assertEqual(len(payment.move_id.line_ids), 4, "3 liquidity lines + 1 counterpart")
        self.assertEqual(sum(lines.mapped("amount_currency")), -100)
        self.assertEqual(lines.mapped("partner_id"), self.partner)
        # amounts that do not divide evenly must not be redistributed
        self.assertEqual(sorted(abs(line.amount_currency) for line in lines), [33.33, 33.33, 33.34])
        self.assertEqual(sorted(lines.mapped("date_maturity")), dates)

        counterpart = self._counterpart_lines(payment)
        self.assertEqual(len(counterpart), 1, "A single counterpart line regardless of the number of checks")
        self.assertEqual(abs(counterpart.amount_currency), 100.0)

        # the old core mechanism posted an extra 'split move'; there must be none
        moves = self.env["account.move"].search(
            [("line_ids.account_id", "=", self.deferred_check_account.id), ("company_id", "=", self.company.id)]
        )
        self.assertEqual(moves, payment.move_id, "Only the payment move should touch the deferred checks account")

    def test_the_lines_are_built_here_when_the_core_does_not(self):
        """Con un core sin parchear el modulo arma las N lineas por su cuenta (tarea 70884).

        Se simula parcheando ``l10n_latam_check`` para que devuelva una sola linea de liquidez, que
        es lo que hace el core vanilla. Sin esto la relocalizacion no tiene cobertura: con la imagen
        parcheada -y en runbot- las lineas las arma el core y nunca se entra por esta rama.
        """
        payment = self._create_own_check_payment([20, 30], numbers=["00000301", "00000302"])
        default_vals = {"name": "test", "amount_currency": -50.0, "balance": -50.0}
        with patch.object(CoreCheckPayment, "_prepare_move_liquidity_lines", lambda self, vals: [dict(vals)]):
            lines = payment._prepare_move_liquidity_lines(default_vals)

        self.assertEqual([line["amount_currency"] for line in lines], [-20.0, -30.0])
        self.assertEqual([line["balance"] for line in lines], [-20.0, -30.0])
        self.assertEqual(
            [line["date_maturity"] for line in lines], payment.l10n_latam_new_check_ids.mapped("payment_date")
        )
        for line, check in zip(lines, payment.l10n_latam_new_check_ids):
            self.assertEqual(line["account_id"], payment.outstanding_account_id.id)
            self.assertIn(check.name, line["name"])
            self.assertEqual(line["l10n_latam_check_ids"], [Command.set(check.ids)])


@tagged("post_install", "-at_install")
class TestOwnChecksMulticurrency(LatamCheckCommon):
    """Own checks in a currency other than the company one."""

    def test_nominal_in_currency_conversion_in_balance(self):
        """Cada cheque guarda su nominal en ``amount_currency`` y la conversion a
        la fecha del pago en ``balance``, linea por linea y en el total."""
        payment = self._create_own_check_payment(
            [20, 30, 70], numbers=["00001001", "00001002", "00001003"], currency=self.foreign_currency
        )
        payment.action_post()

        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
        lines = self._check_lines(payment)
        for line in lines:
            self.assertEqual(line.currency_id, self.foreign_currency)
            expected = self.foreign_currency._convert(
                abs(line.amount_currency), self.company_currency, self.company, payment.date
            )
            self.assertEqual(abs(line.balance), expected, "Balance must be the nominal converted at the payment date")

        self.assertEqual(sum(lines.mapped("amount_currency")), -120)
        expected_total = self.foreign_currency._convert(120, self.company_currency, self.company, payment.date)
        self.assertEqual(abs(sum(lines.mapped("balance"))), expected_total)

    def _create_payment_at_an_odd_rate(self, numbers):
        """Dos cheques iguales a una cotización que no divide exacto, para que el resto exista.

        Con la del fixture (100) la conversión da al centavo y no habría resto que repartir.
        """
        odd_date = fields.Date.add(self.today, days=60)
        self.env["res.currency.rate"].create(
            {
                "name": odd_date,
                "currency_id": self.foreign_currency.id,
                "company_id": self.company.id,
                "rate": 1 / 40.189,
            }
        )
        return self._create_own_check_payment(
            [39717.71, 39717.71], numbers=numbers, currency=self.foreign_currency, date=odd_date
        )

    def test_all_checks_take_the_rate_the_entry_already_used(self):
        """Ticket 123832: todos los cheques se valúan a la cotización que el asiento dio por buena.

        Vencimientos distintos a propósito: la cotización del fixture pasa de 100 a 200 entre ambas
        fechas, así que valuando cada cheque a la fecha de SU vencimiento uno valdría el doble que
        el otro y el asiento no cerraría. Con el cheque diferido de este mismo test alcanza: nunca
        hicieron falta dos o más, aunque el ticket se reportó así.
        """
        payment = self._create_own_check_payment(
            [50, 50],
            numbers=["00001401", "00001402"],
            currency=self.foreign_currency,
            check_dates=[self.today, fields.Date.add(self.today, days=30)],
        )
        payment.action_post()

        self.assert_move_balanced(payment.move_id)
        self.assertEqual(
            [abs(line.balance) for line in self._check_lines(payment)],
            [5000.0, 5000.0],
            "Mismo importe, mismo valor, aunque venzan en fechas con cotización distinta",
        )

    def test_the_counterpart_keeps_the_rounding_residue(self):
        """El resto de redondear cada cheque por separado queda en la contrapartida.

        Las cifras se afirman explícitamente, porque que el asiento cierre no dice DÓNDE quedó el
        resto.
        """
        payment = self._create_payment_at_an_odd_rate(["00001501", "00001502"])
        payment.action_post()

        self.assert_move_balanced(payment.move_id)
        self.assertEqual(
            [abs(line.balance) for line in self._check_lines(payment)],
            [1596215.05, 1596215.05],
            "Cada cheque: 39.717,71 x 40,189 redondeado",
        )
        self.assertEqual(
            abs(self._counterpart_lines(payment).balance), 3192430.10, "La contrapartida se queda con el centavo"
        )
        # convertir el total de una sola vez daría 3.192.430,09: ese centavo es el resto que la
        # contrapartida se queda, y es lo que se afirma arriba

    def test_write_off_does_not_leave_the_residue_homeless(self):
        """Con write-off la contrapartida igual absorbe el resto: si no, el centavo del redondeo por
        línea queda sin dueño y el asiento no cierra."""
        payment = self._create_payment_at_an_odd_rate(["00001801", "00001802"])
        write_off = [
            {
                "name": "ajuste",
                "account_id": self.deferred_check_account.id,
                "currency_id": self.company_currency.id,
                "amount_currency": -100.0,
                "balance": -100.0,
            }
        ]
        res = payment._prepare_move_lines_per_type(write_off_line_vals=write_off)

        self.assertEqual(
            self.company_currency.round(sum(line["balance"] for lines in res.values() for line in lines)),
            0.0,
            "El asiento cierra con el write-off adentro",
        )

    def test_a_netted_amount_recovers_the_payment_rate(self):
        """Si el importe llega neteado (retenciones), la cotización se recupera igual.

        El core le resta la retención al balance de liquidez, así que se la sumamos de vuelta —
        siempre en moneda de compañía, sin mezclar — y los cheques quedan a la cotización del pago
        como cualquier otro pago. Acá se simula el neteo pasando un `balance` ya restado; la
        cobertura de punta a punta vive fuera de este archivo y hay que correrla junto con esta
        suite: `account_payment_pro:TestPaymentChecks` (mismo repo, cheques con Pagos Pro) y
        `l10n_ar_tax:TestPaymentChecksWithholding` (retenciones + cheques, otro repo — o sea que el
        CI de este repo no ve el caso neteado de punta a punta).
        """
        payment = self._create_own_check_payment(
            [50, 50], numbers=["00001601", "00001602"], currency=self.foreign_currency
        )
        # el core entrega el balance ya neteado: 100 x 100 = 10.000 menos 2.000 de retención, y el
        # nominal también neteado. La retención se simula acá porque su fixture vive en `l10n_ar_tax`.
        with patch.object(type(payment), "_prepare_move_withholding_lines", return_value=[{"balance": -2000.0}]):
            lines = payment._prepare_move_liquidity_lines(
                {"name": "test", "amount_currency": -80.0, "balance": -8000.0}
            )
        self.assertEqual(
            [line["balance"] for line in lines],
            [-5000.0, -5000.0],
            "Devolviendo la retención: (8.000 + 2.000) / 100 = 100, la cotización del pago",
        )


@tagged("post_install", "-at_install")
class TestOwnChecksLifecycle(LatamCheckCommon):
    """Draft / post / cancel / reset-to-draft and issue_state transitions."""

    def test_draft_check_is_debited_today(self):
        """EQUIVALENCE (task 70884, BUG-1: draft issue_state).

        Un cheque propio en borrador -que nunca se entrego- sale 'debited', porque el estado se
        decide por metodo de pago y su linea de liquidez todavia no existe. Es un defecto conocido y
        arreglarlo es otro PR.

        Cancelar el pago SI funciona: el guard de ``_get_reconciled_checks_error`` mira la cuenta de
        la linea, que en borrador no hay.
        """
        payment = self._create_own_check_payment([100], numbers=["00002101"])

        self.assertEqual(payment.l10n_latam_new_check_ids.issue_state, "debited")
        self.assertFalse(payment.l10n_latam_new_check_ids.outstanding_line_id)
        payment.action_cancel()
        self.assertEqual(payment.state, "canceled")

    @mute_logger("odoo.sql_db")
    def test_two_draft_payments_cannot_repeat_a_number_today(self):
        """EQUIVALENCE (task 70884, BUG-1: draft issue_state).

        Same root cause, pinned because the relocation reproduces it: the ux
        unique index covers checks with an issue_state, and since drafts now get
        one, two *draft* payments sharing a number already hit the database
        constraint, which should only happen for handed checks. Separate PR.
        """
        self._create_own_check_payment([100], numbers=["00002301"])
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self._create_own_check_payment([100], numbers=["00002301"])

    @mute_logger("odoo.sql_db")
    def test_check_number_is_unique_per_payment_method_line(self):
        """El numero de cheque propio es unico por linea de metodo de pago (o
        sea, por chequera / diario emisor): repetirlo en el mismo diario da
        error, pero el mismo numero puede existir en otro diario, porque cada
        banco numera sus cheques por su cuenta."""
        first = self._create_own_check_payment([100], numbers=["00002401"])
        first.action_post()

        other_journal = self.env["account.journal"].create(
            {"name": "Test Checks Bank 2", "code": "TCKB2", "type": "bank", "company_id": self.company.id}
        )
        other_line = self._add_method_line(
            other_journal, self.own_checks_method, "Own Checks 2", self.deferred_check_account
        )
        other_bank = self._create_own_check_payment([100], numbers=["00002401"], method_line=other_line)
        other_bank.action_post()
        self.assertEqual(other_bank.move_id.state, "posted", "Another journal may re-use the number")

        with self.assertRaises(IntegrityError), self.cr.savepoint():
            second = self._create_own_check_payment([100], numbers=["00002401"])
            second.action_post()

    def test_reset_to_draft_keeps_checks_linked_and_can_post_again(self):
        payment = self._create_own_check_payment([20, 30, 70], numbers=["00002501", "00002502", "00002503"])
        payment.action_post()
        payment.action_draft()

        self.assertEqual(payment.state, "draft")
        for check in payment.l10n_latam_new_check_ids:
            self.assertEqual(
                check.outstanding_line_id.move_id,
                payment.move_id,
                "There is no split move to unlink, checks stay linked to the payment move",
            )

        payment.action_post()
        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)

    def test_legacy_split_move_is_still_unlinked(self):
        """Un pago posteado antes de este cambio apunta a un asiento de split aparte, y al volver a
        borrador se sigue desarmando. Se llama al metodo directo porque su gancho -``button_draft``
        de ``account.move``- solo existe con el core sin parchear.
        """
        payment = self._create_own_check_payment([100], numbers=["00002601"])
        payment.action_post()
        check = payment.l10n_latam_new_check_ids
        split_move = self.env["account.move"].create(
            {
                "journal_id": payment.journal_id.id,
                "line_ids": [
                    Command.create(
                        {"name": "legacy split", "account_id": self.deferred_check_account.id, "debit": 100.0}
                    ),
                    Command.create(
                        {"name": "legacy split", "account_id": self.deferred_check_account.id, "credit": 100.0}
                    ),
                ],
            }
        )
        split_move.action_post()
        check.outstanding_line_id = split_move.line_ids[0]

        payment._l10n_latam_check_unlink_split_move()

        self.assertFalse(split_move.exists(), "The legacy split move must be dropped")
        self.assertTrue(payment.move_id.exists(), "The payment move is not the split move")

    def test_void_affects_only_its_check_and_blocks_reset_to_draft(self):
        """Anular 1 de 3 cheques: el cheque queda anulado y su linea conciliada
        contra un asiento de anulacion que devuelve exactamente su nominal; los
        otros dos siguen entregados y pendientes; y el pago ya no puede volver a
        borrador porque uno de sus cheques dejo de ser reversible.

        Es la prueba de que la anulacion es *por cheque*: con una sola linea de
        liquidez agrupada no habria forma de devolver solo estos 30.
        """
        payment = self._create_own_check_payment([20, 30, 70], numbers=["00002801", "00002802", "00002803"])
        payment.action_post()
        target = payment.l10n_latam_new_check_ids[1]

        target.action_void()

        self.assertEqual(target.issue_state, "voided")
        siblings = payment.l10n_latam_new_check_ids - target
        self.assertEqual(siblings.mapped("issue_state"), ["handed", "handed"])
        for check in siblings:
            self.assertTrue(check.outstanding_line_id.amount_residual, "Siblings must stay outstanding")

        void_move = target.outstanding_line_id.matched_debit_ids.debit_move_id.move_id
        self.assertTrue(void_move, "Voiding reconciles the check line against a new entry")
        self.assert_move_balanced(void_move)
        self.assertEqual(
            abs(
                sum(
                    void_move.line_ids.filtered(lambda x: x.account_id == self.deferred_check_account).mapped("balance")
                )
            ),
            30.0,
            "Only the voided check amount goes back",
        )

        with self.assertRaises(UserError):
            payment.action_draft()

    def test_payment_amount_follows_the_checks(self):
        """El importe del pago lo mandan los cheques: cambiar un cheque lo
        recalcula, y forzar un importe que no coincide bloquea el posteo."""
        payment = self._create_own_check_payment([20, 30], numbers=["00003101", "00003102"])
        payment.l10n_latam_new_check_ids[0].amount = 25
        self.assertEqual(payment.amount, 55, "The payment amount follows the checks")
        payment.action_post()
        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)

        mismatched = self._create_own_check_payment([50, 50], numbers=["00003201", "00003202"])
        mismatched.write({"amount": 120})
        with self.assertRaises(ValidationError):
            mismatched.action_post()


@tagged("post_install", "-at_install")
class TestOwnChecksDraftResync(LatamCheckCommon):
    """Re-synchronization while the move is still in draft.

    ``_synchronize_to_moves`` returns early on posted moves, so this is the only
    state where the core mapping (and the guard the patch comments out) actually
    runs on a payment carrying several liquidity lines.
    """

    def test_removing_a_check_drops_its_liquidity_line(self):
        """The mapping has to delete the liquidity line left over when a check
        goes away, which is where the patch swapped ``Command.delete`` for
        ``Command.unlink``."""
        payment = self._create_own_check_payment([20, 30, 70], numbers=["00005001", "00005002", "00005003"])
        payment.action_post()
        payment.action_draft()

        payment.write({"l10n_latam_new_check_ids": [Command.delete(payment.l10n_latam_new_check_ids[0].id)]})

        self.assertEqual(payment.amount, 100)
        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
        self.assertEqual(len(payment.move_id.line_ids), 3, "2 liquidity lines + 1 counterpart")

    def test_internal_transfer_with_several_own_checks(self):
        """Internal transfer: the counterpart is a single line on the transfer
        account (which the patched mapping classifies apart), and it survives a
        re-sync in draft."""
        destination = self.env["account.journal"].create(
            {"name": "Test Transfer Destination", "code": "TDSTJ", "type": "cash", "company_id": self.company.id}
        )
        self._add_method_line(destination, self.manual_in_method, "Manual", self.manual_outstanding_account)
        payment = self._create_own_check_payment([40, 60], numbers=["00005101", "00005102"])
        payment.write({"is_internal_transfer": True, "destination_journal_id": destination.id})
        payment.action_post()

        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
        transfer_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.company.transfer_account_id
        )
        self.assertEqual(len(transfer_lines), 1, "A single line on the transfer account")
        self.assertTrue(payment.paired_internal_transfer_payment_id)
        self.assert_move_balanced(payment.paired_internal_transfer_payment_id.move_id)

        payment.action_draft()
        payment.write({"amount": payment.amount})
        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)


@tagged("post_install", "-at_install")
class TestCheckViews(LatamCheckCommon):
    def test_check_form_has_no_journal_entry_button(self):
        """Tripwire de la relocation, no una verificacion de UI.

        El parche de core borra ``action_show_journal_entry`` y su boton (con el
        asiento por cheque ya no apunta a nada util). Un modulo no puede borrar
        un metodo de core, asi que al despatchar core el boton vuelve a
        aparecer y hay que taparlo con un override de vista. Este test esta en
        verde hoy y se pone en rojo exactamente en ese momento: es lo unico del
        harness que avisa que falta ese override.
        """
        view = self.env.ref("l10n_latam_check.l10n_latam_check_view_form")
        arch = self.env["l10n_latam.check"].get_view(view.id, "form")["arch"]
        self.assertNotIn("action_show_journal_entry", arch)


@tagged("post_install", "-at_install")
class TestOwnChecksReconciliation(LatamCheckCommon):
    """Own checks against debt, and what happens after the bank debits them."""

    def test_payment_reconciles_the_debt(self):
        payment = self._create_own_check_payment([20, 30, 70], numbers=["00004001", "00004002", "00004003"])
        debt_line = self._create_debt_move(120, account=payment.destination_account_id)
        payment.action_post()

        counterpart = self._counterpart_lines(payment)
        self.assertEqual(len(counterpart), 1, "A single counterpart line regardless of the number of checks")
        (counterpart + debt_line).reconcile()
        self.assertEqual(debt_line.amount_residual, 0.0, "The debt must be fully paid")
        self.assertEqual(
            payment.l10n_latam_new_check_ids.mapped("issue_state"),
            ["handed"] * 3,
            "Paying the debt does not debit the checks",
        )

    def test_debit_one_check_of_many(self):
        """El wizard debita un cheque de N: solo ese queda debitado, el asiento
        de debito mueve exactamente su nominal y queda alcanzable desde el
        cheque."""
        payment = self._create_own_check_payment([20, 30, 70], numbers=["00004101", "00004102", "00004103"])
        payment.action_post()
        target = payment.l10n_latam_new_check_ids[2]

        wizard = (
            self.env["account.check.action.wizard"]
            .with_context(active_model="l10n_latam.check", active_ids=target.ids)
            .create({"date": self.today})
        )
        wizard.action_confirm()

        self.assertEqual(target.issue_state, "debited")
        self.assertFalse(target.outstanding_line_id.amount_residual)
        self.assertTrue(target._get_reconciled_move(), "The debit entry must be reachable from the check")
        self.assertEqual((payment.l10n_latam_new_check_ids - target).mapped("issue_state"), ["handed", "handed"])

        debit_lines = self.env["account.move.line"].search(
            [("account_id", "=", self.manual_outstanding_account.id), ("company_id", "=", self.company.id)]
        )
        self.assertEqual(abs(sum(debit_lines.mapped("balance"))), 70.0, "Only the debited check amount must be moved")

    def test_debit_guards(self):
        """El wizard de debito no corre si el diario no lo habilita, ni con una
        fecha anterior a la del pago."""
        payment = self._create_own_check_payment([50], numbers=["00004301"])
        payment.action_post()

        past_wizard = (
            self.env["account.check.action.wizard"]
            .with_context(active_model="l10n_latam.check", active_ids=payment.l10n_latam_new_check_ids.ids)
            .create({"date": fields.Date.subtract(self.today, days=5)})
        )
        with self.assertRaisesRegex(UserError, "no puede ser inferior"):
            past_wizard.action_confirm()

        self.bank_journal.check_add_debit_button = False
        wizard = (
            self.env["account.check.action.wizard"]
            .with_context(active_model="l10n_latam.check", active_ids=payment.l10n_latam_new_check_ids.ids)
            .create({"date": self.today})
        )
        with self.assertRaisesRegex(UserError, "Add Debit Date"):
            wizard.action_confirm()
