##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestOwnChecksNonReconcilable(AccountTestInvoicingCommon):
    """Cuando la cuenta de cheques propios no permite conciliación, el issue_state se fuerza a
    'debited' porque el residual de la línea es 0 por definición. Ese débito es nominal (no hay
    asiento de débito conciliado), así que no debe impedir volver el pago a borrador ni cancelarlo.
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
                }
            )
        ]
        cls.own_checks_payment_method_line = cls.bank_journal.outbound_payment_method_line_ids.filtered(
            lambda x: x.code == "own_checks"
        )
        cls.own_checks_account = cls.outbound_payment_method_line.payment_account_id.copy()
        cls.own_checks_payment_method_line.payment_account_id = cls.own_checks_account

    def _create_own_check_payment(self, number, amount=50):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_id": self.partner_a.id,
                "journal_id": self.bank_journal.id,
                "payment_method_line_id": self.own_checks_payment_method_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": number,
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": amount,
                        }
                    )
                ],
            }
        )
        payment.action_post()
        return payment

    def test_draft_own_check_with_non_reconcilable_account(self):
        """Con cuenta no conciliable el cheque queda debitado, pero el pago debe poder volver a borrador."""
        self.own_checks_account.reconcile = False
        payment = self._create_own_check_payment("00000010")

        self.assertEqual(
            payment.l10n_latam_new_check_ids.issue_state,
            "debited",
            "Con cuenta no conciliable el cheque se fuerza a debitado.",
        )

        payment.action_draft()
        self.assertEqual(payment.state, "draft", "El pago debería poder volver a borrador.")

    def test_cancel_own_check_with_non_reconcilable_account(self):
        """Mismo escenario que el anterior, pero cancelando el pago."""
        self.own_checks_account.reconcile = False
        payment = self._create_own_check_payment("00000011")

        payment.action_cancel()
        self.assertEqual(payment.state, "canceled", "El pago debería poder cancelarse.")

    def test_draft_own_check_with_reconcilable_account_is_blocked(self):
        """No regresión: con cuenta conciliable y cheque anulado, Odoo sigue bloqueando el borrador."""
        self.assertTrue(
            self.own_checks_account.reconcile,
            "La cuenta de cheques propios debería ser conciliable por defecto.",
        )
        payment = self._create_own_check_payment("00000012")
        check = payment.l10n_latam_new_check_ids
        check.action_void()
        self.assertEqual(check.issue_state, "voided")

        with self.assertRaises(UserError):
            payment.action_draft()
