##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Third party checks: reception, endorsement, deposit and rejection.

The core patch this suite guards also rewrites the liquidity lines of third
party check payments (not only own checks): one line per check instead of a
single grouped line. Everything asserted here is what a relocation of that
patch into our modules must keep working. Part of the harness of task 70884.
"""

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestThirdPartyChecksEntry(LatamCheckCommon):
    """Journal entry shape when receiving / delivering third party checks."""

    def test_receive_checks(self):
        """Recibir N cheques: una linea de liquidez por cheque en la cuenta de
        cheques de terceros, cheques en cartera, sin issue_state (es solo de
        cheques propios) y con outstanding_line_id apuntando al asiento del pago.

        Ese ultimo punto es nuevo del parche: los consumidores de
        ``outstanding_line_id`` (reportes, wizards, el recompute de
        ``account.account``) ahora tambien ven cheques de terceros.
        """
        payment = self._receive_third_party_checks([55, 45], numbers=["00010001", "00010002"])
        payment.action_post()

        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
        self.assertEqual(payment.amount, 100)
        self.assertEqual(len(payment.move_id.line_ids), 3, "2 liquidity lines + 1 counterpart")
        for line in self._check_lines(payment):
            self.assertEqual(line.account_id, self.third_party_account)
            self.assertGreater(line.amount_currency, 0, "Receiving checks debits the check account")

        checks = payment.l10n_latam_new_check_ids
        self.assertEqual(checks.mapped("current_journal_id"), self.third_party_journal)
        self.assertFalse(any(checks.mapped("issue_state")), "issue_state is only for own checks")
        for check in checks:
            self.assertEqual(check.outstanding_line_id.move_id, payment.move_id)
            self.assertEqual(abs(check.outstanding_line_id.amount_currency), check.amount)

    def test_deliver_checks_to_vendor(self):
        """Endosar N cheques: una linea por cheque, cheques fuera de cartera,
        operacion trackeada, y el ``outstanding_line_id`` pasa a apuntar al
        asiento del endoso (es un Many2one: gana la ultima operacion)."""
        payment = self._receive_third_party_checks([55, 45], numbers=["00010301", "00010302"])
        payment.action_post()
        checks = payment.l10n_latam_new_check_ids

        delivery = self._deliver_third_party_checks(checks)
        delivery.action_post()

        self.assert_move_balanced(delivery.move_id)
        self.assertEqual(delivery.amount, 100)
        self.assertEqual(len(self._check_lines(delivery)), 2, "One line per delivered check")
        for line in self._check_lines(delivery):
            self.assertLess(line.amount_currency, 0, "Delivering checks credits the check account")
        self.assertFalse(checks.mapped("current_journal_id"), "Delivered checks are no longer on hand")
        self.assertEqual(checks.mapped("outstanding_line_id.move_id"), delivery.move_id)
        self.assertEqual(checks[0].operation_ids, delivery)
        self.assertEqual(checks[0]._get_last_operation(), delivery)


@tagged("post_install", "-at_install")
class TestThirdPartyChecksGuards(LatamCheckCommon):
    """Blocking validations of l10n_latam_check + l10n_latam_check_ux."""

    def test_cannot_deliver_a_draft_check(self):
        payment = self._receive_third_party_checks([55], numbers=["00011001"])
        delivery = self._deliver_third_party_checks(payment.l10n_latam_new_check_ids)
        with self.assertRaises(ValidationError):
            delivery.action_post()

    def test_cannot_deliver_the_same_check_twice(self):
        payment = self._receive_third_party_checks([55], numbers=["00011101"])
        payment.action_post()
        check = payment.l10n_latam_new_check_ids

        first = self._deliver_third_party_checks(check)
        first.action_post()
        second = self._deliver_third_party_checks(check)
        with self.assertRaises(ValidationError):
            second.action_post()

    def test_cannot_confirm_the_same_check_in_two_payments_at_once(self):
        """l10n_latam_check_ux guard: two draft payments sharing a check."""
        payment = self._receive_third_party_checks([55], numbers=["00011201"])
        payment.action_post()
        check = payment.l10n_latam_new_check_ids

        first = self._deliver_third_party_checks(check)
        second = self._deliver_third_party_checks(check)
        with self.assertRaises(ValidationError):
            (first + second).action_post()

    def test_duplicated_third_party_check_number_warns(self):
        payment = self._receive_third_party_checks([55], numbers=["00011301"])
        payment.action_post()

        duplicated = self._receive_third_party_checks([55], numbers=["00011301"])
        self.assertTrue(duplicated.l10n_latam_check_warning_msg, "Receiving a check with an existing number must warn")
        with self.assertRaises(ValidationError):
            duplicated.action_post()

    def test_reset_to_draft_blocked_when_not_last_operation(self):
        payment = self._receive_third_party_checks([55], numbers=["00011401"])
        payment.action_post()
        delivery = self._deliver_third_party_checks(payment.l10n_latam_new_check_ids)
        delivery.action_post()

        with self.assertRaises(ValidationError):
            payment.action_draft()

    def test_payment_method_line_with_checks_cannot_be_deleted(self):
        payment = self._receive_third_party_checks([55], numbers=["00011501"])
        payment.action_post()

        with self.assertRaises(UserError):
            self.new_third_party_line.unlink()


@tagged("post_install", "-at_install")
class TestThirdPartyChecksDeposit(LatamCheckCommon):
    """Depositing third party checks into a bank journal (mass transfer)."""

    def _deposit(self, checks, split=False):
        wizard = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=checks.ids)
            .create(
                {
                    "journal_id": self.third_party_journal.id,
                    "destination_journal_id": self.bank_journal.id,
                    "payment_date": self.today,
                    "split_payment": split,
                }
            )
        )
        return wizard._create_payments()

    def test_deposit_to_bank(self):
        """Depositar N cheques: quedan en el diario banco, la transferencia
        saliente y su par entrante se concilian, y el asiento **bancario** queda
        partido en una linea por cheque (antes era una sola linea agrupada: eso es lo
        que ve la conciliacion bancaria)."""
        payment = self._receive_third_party_checks([55, 45], numbers=["00012001", "00012002"])
        payment.action_post()
        checks = payment.l10n_latam_new_check_ids

        self._deposit(checks)

        self.assertEqual(checks.mapped("current_journal_id"), self.bank_journal)
        operations = checks.operation_ids
        self.assertEqual(len(operations), 2, "An outbound transfer and its paired inbound payment")
        for operation in operations:
            self.assert_move_balanced(operation.move_id)

        outbound = operations.filtered(lambda p: p.payment_type == "outbound")
        self.assertEqual(outbound.payment_method_line_id.code, "out_third_party_checks")
        self.assertTrue(
            outbound.move_id.line_ids.mapped("full_reconcile_id"), "Both sides of the transfer must reconcile"
        )

        inbound = operations.filtered(lambda p: p.payment_type == "inbound")
        self.assertEqual(inbound.journal_id, self.bank_journal)
        self.assertEqual(len(self._check_lines(inbound)), 2, "One bank line per deposited check")

    def test_split_deposit_creates_one_payment_per_check(self):
        payment = self._receive_third_party_checks([55, 45], numbers=["00012301", "00012302"])
        payment.action_post()
        checks = payment.l10n_latam_new_check_ids

        self._deposit(checks, split=True)

        outbounds = checks.operation_ids.filtered(lambda p: p.payment_type == "outbound")
        self.assertEqual(len(outbounds), 2, "One transfer per check")
        for outbound in outbounds:
            self.assertEqual(len(outbound.l10n_latam_move_check_ids), 1)
            self.assert_move_balanced(outbound.move_id)


@tagged("post_install", "-at_install")
class TestThirdPartyChecksRejection(LatamCheckCommon):
    """Rejection of an endorsed / deposited third party check."""

    def test_endorsed_check_rejection(self):
        """Rechazo de un cheque endosado: se recupera del proveedor, se devuelve
        al cliente (reabriendo la deuda) y todos los asientos balancean.

        Solo se puede rechazar lo que salio de cartera: en cartera no hay nada
        que rechazar."""
        payment = self._receive_third_party_checks([55], numbers=["00013001"])
        payment.action_post()
        check = payment.l10n_latam_new_check_ids
        self.assertFalse(check.can_reject, "A check still on hand has nothing to reject")

        delivery = self._deliver_third_party_checks(check)
        delivery.action_post()

        self.assertTrue(check.can_reject)
        wizard = (
            self.env["account.check.reject.wizard"]
            .with_context(active_model="l10n_latam.check", active_ids=check.ids)
            .create({"date": self.today, "rejected_journal_id": self.rejected_journal.id})
        )
        wizard.action_confirm()

        codes = check.operation_ids.mapped("payment_method_line_id.code")
        self.assertIn("in_third_party_checks", codes, "The check is recovered from the vendor")
        self.assertIn("out_third_party_checks", codes)
        for operation in check.operation_ids:
            self.assert_move_balanced(operation.move_id)

        customer_return = check.operation_ids.filtered(
            lambda p: p.partner_type == "customer" and p.payment_type == "outbound"
        )
        self.assertTrue(customer_return, "The check must be returned to the customer, re-opening the debt")
        self.assertEqual(customer_return.partner_id, self.partner)
        self.assertEqual(customer_return.amount, 55)


@tagged("post_install", "-at_install")
class TestThirdPartyChecksMulticurrency(LatamCheckCommon):
    """Third party checks in a currency other than the company one."""

    def test_receive_and_deliver_foreign_currency_checks(self):
        """Recepcion y endoso en moneda extranjera: en las dos puntas cada cheque
        conserva su nominal y convierte a la fecha de su propio pago."""
        payment = self._receive_third_party_checks(
            [55, 45], numbers=["00014001", "00014002"], currency=self.foreign_currency
        )
        payment.action_post()
        checks = payment.l10n_latam_new_check_ids

        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
        for line in self._check_lines(payment):
            expected = self.foreign_currency._convert(
                abs(line.amount_currency), self.company_currency, self.company, payment.date
            )
            self.assertEqual(abs(line.balance), expected)

        delivery = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner.id,
                "journal_id": self.third_party_journal.id,
                "company_id": self.company.id,
                "date": self.today,
                "currency_id": self.foreign_currency.id,
                "payment_method_line_id": self.out_third_party_line.id,
                "l10n_latam_move_check_ids": [Command.set(checks.ids)],
            }
        )
        delivery.action_post()

        self.assert_move_balanced(delivery.move_id)
        self.assert_check_lines_match(delivery)
