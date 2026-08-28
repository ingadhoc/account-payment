# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCheckOperationOrder(AccountTestInvoicingCommon):
    """El orden de la cadena de operaciones de un cheque lo da la confirmación, no el borrador.

    De ese orden dependen el diario actual del cheque (si sigue en cartera) y el bloqueo para
    restablecer un pago a borrador. Cuando el orden se deduce de ``create_date``, una orden de pago
    que estuvo un rato en borrador queda al principio de la cadena aunque se confirme última: el
    cheque entregado sigue figurando disponible y la OP no se puede corregir (tickets 126339 y
    126474).

    El setup no usa ``L10nLatamCheckTest``: ese common arma una compañía argentina con
    ``setup_other_company()``, y sobre una base con ``saas_client_account`` instalado eso choca
    contra su constraint de moneda-vs-país. Armamos el diario acá, como ya hace
    ``test_check_payment_journal_entry``.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Diario de efectivo con cheques de terceros: es el tipo de diario donde el core habilita
        # estos métodos de pago, y liquidan contra una cuenta puente, no contra la de efectivo.
        cls.check_journal = cls.env["account.journal"].create(
            {
                "name": "Third Party Checks Order",
                "code": "TPCOR",
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
                "outbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_out_third_party_checks"
                            ).id,
                            "payment_account_id": cls.outbound_payment_method_line.payment_account_id.id,
                        }
                    )
                ],
            }
        )
        cls.in_check_line = cls.check_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks"
        )
        cls.out_check_line = cls.check_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.code == "out_third_party_checks"
        )

    def _create_receipt(self, check_number="00000101"):
        """Recibo de cliente donde nace el cheque de terceros."""
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "inbound",
                "journal_id": self.check_journal.id,
                "payment_method_line_id": self.in_check_line.id,
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
        return payment

    def _create_draft_delivery(self):
        """Orden de pago a proveedor, todavía sin el cheque cargado."""
        return self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "outbound",
                "amount": 100.0,
                "journal_id": self.check_journal.id,
                "payment_method_line_id": self.out_check_line.id,
            }
        )

    def _force_create_date(self, payment, create_date):
        """``create_date`` no es escribible por ORM y es justamente la variable del caso."""
        self.env.cr.execute(
            "UPDATE account_payment SET create_date = %s WHERE id = %s",
            (create_date, payment.id),
        )
        payment.invalidate_recordset(["create_date"])

    def _deliver_check_created_before_the_receipt(self, check_number="00000101"):
        """Reproduce el flujo reportado: OP en borrador → recibo confirmado → OP confirmada."""
        delivery = self._create_draft_delivery()
        self._force_create_date(delivery, "2026-08-25 09:00:00")

        receipt = self._create_receipt(check_number)
        check = receipt.l10n_latam_new_check_ids
        self._force_create_date(receipt, "2026-08-25 11:00:00")

        delivery.l10n_latam_move_check_ids = [Command.set(check.ids)]
        delivery.action_post()
        return receipt, delivery, check

    def test_delivery_confirmed_last_is_the_last_operation(self):
        """Confirmar último deja al pago último en la cadena, aunque su borrador sea el más viejo."""
        receipt, delivery, check = self._deliver_check_created_before_the_receipt("00000101")

        self.assertEqual(
            check._get_last_operation(),
            delivery,
            "La última operación del cheque debe ser la entrega, que fue lo último confirmado.",
        )
        self.assertGreater(
            delivery.l10n_latam_move_check_ids_operation_date,
            receipt.l10n_latam_move_check_ids_operation_date,
            "La entrega se confirmó después del recibo, su fecha de operación debe ser posterior.",
        )

    def test_delivered_check_is_not_available_anymore(self):
        """El síntoma de los tickets: el cheque entregado seguía disponible en la cartera."""
        __, __, check = self._deliver_check_created_before_the_receipt("00000102")

        self.assertFalse(
            check.current_journal_id,
            "El cheque entregado a un proveedor no debe seguir disponible en la cartera.",
        )

    def test_delivery_can_be_reset_to_draft(self):
        """El otro síntoma: no dejaba corregir la OP porque la creía anterior al recibo."""
        __, delivery, __ = self._deliver_check_created_before_the_receipt("00000103")

        delivery.action_draft()

        self.assertEqual(delivery.state, "draft")

    def test_receipt_cannot_be_reset_to_draft_once_delivered(self):
        """Contracara: con la cadena bien ordenada, el recibo ya no es la última operación.

        Es lo que protege el caso del ticket 123455, donde re-confirmar el recibo lo mandaba al
        final de la cadena y devolvía el cheque a la cartera.
        """
        receipt, __, __ = self._deliver_check_created_before_the_receipt("00000104")

        with self.assertRaisesRegex(ValidationError, "not the last operation"):
            receipt.action_draft()

    def test_operations_confirmed_in_the_same_second_do_not_tie(self):
        """Dos pagos creados en el mismo instante igual tienen que quedar ordenados."""
        delivery = self._create_draft_delivery()
        self._force_create_date(delivery, "2026-08-25 09:00:00")

        receipt = self._create_receipt("00000105")
        check = receipt.l10n_latam_new_check_ids
        self._force_create_date(receipt, "2026-08-25 09:00:00")

        delivery.l10n_latam_move_check_ids = [Command.set(check.ids)]
        delivery.action_post()

        self.assertNotEqual(
            delivery.l10n_latam_move_check_ids_operation_date,
            receipt.l10n_latam_move_check_ids_operation_date,
            "Dos operaciones del mismo cheque no pueden compartir fecha de operación.",
        )
        self.assertEqual(check._get_last_operation(), delivery)
