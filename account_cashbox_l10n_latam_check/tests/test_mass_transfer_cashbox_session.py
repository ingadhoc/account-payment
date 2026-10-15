from odoo import Command, fields
from odoo.addons.l10n_latam_check.tests.common import L10nLatamCheckTest
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install_l10n", "post_install", "-at_install")
class TestMassTransferCashboxSession(L10nLatamCheckTest):
    """La transferencia de cheques de terceros toma la sesión de caja abierta del
    diario destino y la deja en el pago, y la exige si el usuario la requiere."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.destination_journal = cls.company_data_3["default_journal_bank"]
        cls.cashbox = cls.env["account.cashbox"].create(
            {
                "name": "Caja cheques",
                "company_id": cls.destination_journal.company_id.id,
                "journal_ids": [Command.link(cls.destination_journal.id)],
                "allow_concurrent_sessions": True,
            }
        )
        cls.session = cls.env["account.cashbox.session"].create({"cashbox_id": cls.cashbox.id, "name": "S-1"})
        cls.session.action_account_cashbox_session_open()

    def _create_check(self):
        journal = self.third_party_check_journal
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "inbound",
                "journal_id": journal.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": "00000001",
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 1,
                        }
                    ),
                ],
                "payment_method_line_id": journal._get_available_payment_method_lines("inbound")
                .filtered(lambda x: x.code == "new_third_party_checks")
                .id,
            }
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _transfer_wizard(self, check):
        return (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=check.ids)
            .create({"destination_journal_id": self.destination_journal.id})
        )

    def test_transfer_takes_destination_session(self):
        check = self._create_check()
        wizard = self._transfer_wizard(check)
        self.assertEqual(wizard.cashbox_session_id, self.session)
        payment = wizard._create_payments()
        self.assertEqual(payment.cashbox_session_id, self.session)

    def test_transfer_requires_session(self):
        check = self._create_check()
        self.env.user.requiere_account_cashbox_session = True
        self.session.action_closing_control()
        wizard = self._transfer_wizard(check)
        self.assertFalse(wizard.cashbox_session_id)
        with self.assertRaisesRegex(UserError, "requires to use payment session"):
            wizard._create_payments()
