# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCheckPaymentJournalEntry(AccountTestInvoicingCommon):
    """El asiento de un pago con cheques no se puede borrar mientras el pago está confirmado.

    Borrarlo y volver a postear el pago —ahora ``account_ux`` regenera el asiento faltante— deja al
    cheque con el diario actual equivocado: ``current_journal_id`` se resuelve por la última
    operación del cheque ordenada por ``(date, write_date, id)``, y el repost mueve el
    ``write_date``, así que una recepción vieja pasa a tapar la transferencia posterior. El camino
    válido para tocar ese asiento es restablecer el pago a borrador.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Diario de efectivo con cheques de terceros nuevos: es el tipo de diario donde el core
        # habilita ese método de pago (``l10n_latam_check/models/account_payment_method.py``), y
        # liquida contra una cuenta puente, no contra la de efectivo.
        cls.check_journal = cls.env["account.journal"].create(
            {
                "name": "Third Party Checks",
                "code": "TPCUX",
                "type": "cash",
                "company_id": cls.company_data["company"].id,
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_new_third_party_checks"
                            ).id,
                            "payment_account_id": cls.inbound_payment_method_line.payment_account_id.id,
                        }
                    )
                ],
            }
        )
        cls.check_payment_method_line = cls.check_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks"
        )

    def _create_third_party_check_payment(self, check_number="00000001"):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_a.id,
                "journal_id": self.check_journal.id,
                "payment_method_line_id": self.check_payment_method_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": check_number,
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 100.0,
                        }
                    )
                ],
            }
        )
        payment.action_post()
        self.assertTrue(payment.move_id, "El pago con cheques se debe crear con su asiento contable.")
        self.assertTrue(payment._is_latam_check_payment())
        return payment

    def test_cannot_delete_journal_entry_of_confirmed_check_payment(self):
        payment = self._create_third_party_check_payment()
        move = payment.move_id
        move.button_draft()

        with self.assertRaisesRegex(UserError, "payment with checks while the payment is confirmed"):
            move.unlink()

        self.assertEqual(payment.move_id, move, "El asiento del pago confirmado no se debe borrar.")

    def test_can_delete_journal_entry_of_draft_check_payment(self):
        """Restablecer el pago a borrador es el camino habilitado para tocarle el asiento."""
        payment = self._create_third_party_check_payment()
        payment.action_draft()

        payment.move_id.unlink()

        self.assertFalse(payment.move_id, "Con el pago en borrador el asiento se debe poder borrar.")

    def test_force_delete_still_deletes_the_journal_entry(self):
        """``force_delete`` sigue siendo la salida programática, igual que en los ondelete de core."""
        payment = self._create_third_party_check_payment()
        move = payment.move_id
        move.button_draft()

        move.with_context(force_delete=True).unlink()

        self.assertFalse(payment.move_id)
