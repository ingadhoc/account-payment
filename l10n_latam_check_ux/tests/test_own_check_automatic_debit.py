# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestOwnChecksAutomaticDebit(AccountTestInvoicingCommon):
    """Cheques propios con débito automático: la cuenta del método de pago no es conciliable.

    En esa configuración el cheque se debita en el momento en que se emite, así que
    ``l10n_latam.check._compute_issue_state`` lo deja siempre en ``debited`` (no hay
    conciliación posterior que lo pueda mover). Como el core bloquea restablecer a borrador
    y cancelar cualquier pago con cheques debitados, el cliente quedaba sin forma de corregir
    el pago. Acá no hay conciliación que romper, así que ese bloqueo no aplica.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.bank_journal.outbound_payment_method_line_ids = [
            Command.create(
                {
                    "payment_method_id": cls.env.ref("l10n_latam_check.account_payment_method_own_checks").id,
                    "name": "Own Checks",
                    "payment_account_id": cls.outbound_payment_method_line.payment_account_id.id,
                }
            )
        ]
        cls.own_checks_method_line = cls.bank_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.code == "own_checks"
        )
        cls.reconcilable_outstanding_account = cls.own_checks_method_line.payment_account_id

    def _create_own_check_payment(self, check_number):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner_a.id,
                "journal_id": self.bank_journal.id,
                "payment_method_line_id": self.own_checks_method_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": check_number,
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 50,
                        }
                    )
                ],
            }
        )
        payment.action_post()
        self.assertTrue(payment._is_latam_check_payment())
        return payment

    def _set_automatic_debit(self):
        """Débito automático: el método de pago liquida contra la cuenta del diario."""
        liquidity_account = self.bank_journal.default_account_id
        self.assertFalse(liquidity_account.reconcile, "La cuenta de liquidez del diario no debería ser conciliable.")
        self.own_checks_method_line.payment_account_id = liquidity_account
        return liquidity_account

    def _debit_check(self, check):
        """Debita el cheque como lo hace el usuario: asiento contra la cuenta de liquidez."""
        outstanding_line = check.outstanding_line_id
        debit_move = self.env["account.move"].create(
            {
                "journal_id": self.bank_journal.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Debit check %s" % check.name,
                            "account_id": outstanding_line.account_id.id,
                            "debit": abs(outstanding_line.balance),
                        }
                    ),
                    Command.create(
                        {
                            "name": "Debit check %s" % check.name,
                            "account_id": self.bank_journal.default_account_id.id,
                            "credit": abs(outstanding_line.balance),
                        }
                    ),
                ],
            }
        )
        debit_move.action_post()
        (outstanding_line + debit_move.line_ids.filtered(lambda line: line.debit)).reconcile()

    def test_automatic_debit_check_can_reset_payment_to_draft(self):
        self._set_automatic_debit()
        payment = self._create_own_check_payment("00000101")

        self.assertEqual(
            payment.l10n_latam_new_check_ids.issue_state, "debited", "Con débito automático el cheque nace debitado."
        )

        payment.action_draft()

        self.assertEqual(payment.state, "draft")
        self.assertEqual(payment.move_id.state, "draft")

    def test_automatic_debit_check_can_be_corrected_and_posted_again(self):
        """El circuito completo del cliente: restablecer, corregir el cheque y volver a confirmar."""
        self._set_automatic_debit()
        payment = self._create_own_check_payment("00000106")

        payment.action_draft()
        payment.l10n_latam_new_check_ids.name = "00000107"
        payment.action_post()

        self.assertEqual(payment.l10n_latam_new_check_ids.name, "00000107")
        self.assertEqual(payment.move_id.state, "posted")

    def test_automatic_debit_check_can_reset_journal_entry_to_draft(self):
        self._set_automatic_debit()
        payment = self._create_own_check_payment("00000102")

        payment.move_id.button_draft()

        self.assertEqual(payment.move_id.state, "draft")

    def test_automatic_debit_check_can_cancel_payment(self):
        self._set_automatic_debit()
        payment = self._create_own_check_payment("00000103")

        payment.action_cancel()

        self.assertEqual(payment.state, "canceled")

    def test_debited_check_on_reconcilable_account_still_blocks_draft(self):
        """La restricción del core sigue viva cuando el cheque se debitó de verdad."""
        self.assertTrue(
            self.reconcilable_outstanding_account.reconcile,
            "La cuenta puente de cheques propios debería ser conciliable.",
        )
        payment = self._create_own_check_payment("00000104")
        check = payment.l10n_latam_new_check_ids
        self.assertEqual(check.issue_state, "handed")

        self._debit_check(check)
        self.assertEqual(check.issue_state, "debited")

        with self.assertRaisesRegex(UserError, "debited or been voided"):
            payment.action_draft()

    def test_voided_check_still_blocks_draft(self):
        payment = self._create_own_check_payment("00000105")
        check = payment.l10n_latam_new_check_ids

        check.action_void()
        self.assertEqual(check.issue_state, "voided")

        with self.assertRaisesRegex(UserError, "debited or been voided"):
            payment.action_draft()
