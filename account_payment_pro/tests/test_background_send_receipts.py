"""Tests del envío en segundo plano de los recibos de pago (tarea 71918).

Renderizar el recibo es caro (retenciones, cheques, comprobantes imputados), así
que el envío múltiple desde la lista se encola y lo hace el cron en vez de
bloquear el request del usuario. Estos tests cubren el encolado, el envío por
cron, el aislamiento de un pago que falla y el desencolado al pasar a borrador.
"""

from unittest.mock import patch

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestBackgroundSendReceipts(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.pay_journal = cls.company_data["default_journal_bank"]
        cls.partner = cls.env["res.partner"].create(
            {"name": "Background Send Partner", "email": "background.send@example.com"}
        )
        cls.payments = cls.env["account.payment"].create(
            [
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": cls.partner.id,
                    "amount": 100.0 + index,
                    "date": fields.Date.today(),
                    "journal_id": cls.pay_journal.id,
                }
                for index in range(3)
            ]
        )
        cls.payments.action_post()
        cls.cron = cls.env.ref("account_payment_pro.ir_cron_background_send_payment_receipts")

    def _run_cron(self, **kwargs):
        """Corre el cron con el commit mockeado: commitear dentro de un test está
        prohibido, y lo que queremos verificar es el envío, no el commit."""
        with patch.object(type(self.env["account.payment"]), "_background_send_commit", lambda *args, **kw: None):
            self.env["account.payment"]._cron_background_send_payment_receipts(**kwargs)

    def _set_batch_size(self, size):
        self.env["ir.config_parameter"].sudo().set_param("account_payment_pro.background_send_batch_size", str(size))

    # -------------------------------------------------------------------------
    # Entrada por UI: el composer de Odoo decide si manda o encola
    # -------------------------------------------------------------------------

    def _composer(self, payments):
        return (
            self.env["mail.compose.message"]
            .with_context(active_model="account.payment", active_ids=payments.ids)
            .create(
                {
                    "composition_mode": "mass_mail",
                    "model": "account.payment",
                    "res_ids": repr(payments.ids),
                    "template_id": self.env.ref("account.mail_template_data_payment_receipt").id,
                }
            )
        )

    def test_small_selection_sends_right_away(self):
        """Hasta el umbral, el botón Enviar del composer manda como siempre."""
        self._set_batch_size(5)
        composer = self._composer(self.payments)
        self.assertFalse(composer.payment_background_send)
        mails_before = self.env["mail.mail"].search_count([])
        composer.action_send_mail()
        self.assertEqual(self.env["mail.mail"].search_count([]) - mails_before, 3)
        self.assertFalse(any(self.payments.mapped("background_send")))

    def test_big_selection_queues_instead_of_sending(self):
        self._set_batch_size(2)
        composer = self._composer(self.payments)
        self.assertTrue(composer.payment_background_send)
        mails_before = self.env["mail.mail"].search_count([])
        action = composer.action_send_mail()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(self.env["mail.mail"].search_count([]), mails_before, "no tiene que mandar nada todavía")
        self.assertTrue(all(self.payments.mapped("background_send")))

    def test_cron_sends_what_the_user_composed(self):
        """El cron manda un mail por pago, con lo que el usuario editó en el
        composer (no el template), y los saca de la cola."""
        self._set_batch_size(2)
        composer = self._composer(self.payments)
        composer.write({"subject": "Recibo editado a mano", "body": "<p>Cuerpo propio del usuario</p>"})
        composer.action_send_mail()

        self._run_cron()

        self.assertFalse(any(self.payments.mapped("background_send")))
        self.assertFalse(any(self.payments.mapped("background_send_data")))
        mails = self.env["mail.mail"].search([("model", "=", "account.payment"), ("res_id", "in", self.payments.ids)])
        self.assertEqual(len(mails), 3)
        self.assertTrue(all(m.subject == "Recibo editado a mano" for m in mails))
        self.assertTrue(all("Cuerpo propio del usuario" in (m.body_html or "") for m in mails))

    @mute_logger("odoo.addons.account_payment_pro.models.account_payment")
    def test_failing_payment_does_not_stop_the_batch(self):
        """Un pago que explota se desencola, deja el error en su chatter y no
        frena a los demás."""
        self.payments._queue_background_send()
        failing = self.payments[1]
        original_send = type(self.env["account.payment"])._background_send_receipt

        def _send(payment_self):
            if payment_self.id == failing.id:
                raise ValueError("boom")
            return original_send(payment_self)

        with patch.object(type(self.env["account.payment"]), "_background_send_receipt", _send):
            self._run_cron()

        self.assertFalse(any(self.payments.mapped("background_send")))
        messages = failing.message_ids.filtered(lambda m: "boom" in (m.body or ""))
        self.assertTrue(messages, "El error tiene que quedar registrado en el chatter del pago")

    # -------------------------------------------------------------------------
    # Bordes
    # -------------------------------------------------------------------------

    def test_draft_or_cancel_dequeues_the_payment(self):
        """Un pago que vuelve a borrador o se cancela sale de la cola: ya no es
        un recibo que el cliente tenga que recibir."""
        to_draft, to_cancel = self.payments[0], self.payments[1]
        (to_draft | to_cancel)._queue_background_send()

        to_draft.action_draft()
        to_cancel.action_cancel()

        self.assertFalse(to_draft.background_send)
        self.assertFalse(to_cancel.background_send)

    def test_cron_ignores_payments_that_are_no_longer_sendable(self):
        """Defensa del dominio del cron: aunque algo quede encolado, un pago
        que ya no está vigente no se manda."""
        self.payments._queue_background_send()
        self.payments[0].action_cancel()
        mails_before = self.env["mail.mail"].search_count([])

        self._run_cron()

        self.assertEqual(self.env["mail.mail"].search_count([]) - mails_before, 2)
