# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleInheritedMove(TransactionCase):
    """Pago confirmado con un método común y convertido después en pago principal de bundle.

    El pago principal sin retenciones ni write-off no lleva asiento (_bypass_journal_entry),
    pero el bypass solo evita generarlo. Si el pago ya tenía asiento de su primera
    confirmación, al pasarlo a borrador y convertirlo en bundle el asiento quedaba y se
    sincronizaba a cero contra la cuenta del diario de pagos múltiples.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Bank Test",
                "type": "bank",
                "code": "BNKBT",
                "company_id": cls.company.id,
            }
        )
        cls.bundle_journal = cls.env["account.journal"].browse(cls.company._get_bundle_journal("outbound"))
        cls.bundle_method_lines = cls.bundle_journal.inbound_payment_method_line_ids.filtered(
            lambda x: x.code == "payment_bundle"
        ) | cls.bundle_journal.outbound_payment_method_line_ids.filtered(lambda x: x.code == "payment_bundle")

    def _post_then_convert_to_bundle(self, payment_type):
        bank_method_lines = (
            self.bank_journal.inbound_payment_method_line_ids
            if payment_type == "inbound"
            else self.bank_journal.outbound_payment_method_line_ids
        )
        payment = self.env["account.payment"].create(
            {
                "payment_type": payment_type,
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "payment_method_line_id": bank_method_lines[:1].id,
                "amount": 1000.0,
            }
        )
        payment.action_post()
        old_move = payment.move_id
        self.assertTrue(old_move)

        payment.action_draft()
        payment.write(
            {
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.bundle_method_lines.filtered(
                    lambda x: x.payment_type == payment_type
                ).id,
                "amount": 0.0,
            }
        )
        self.assertTrue(payment.is_main_payment)
        payment.action_post()
        return payment, old_move

    def test_outbound_converted_to_bundle_drops_old_move(self):
        payment, old_move = self._post_then_convert_to_bundle("outbound")
        self.assertFalse(payment.move_id)
        self.assertFalse(old_move.exists())
        self.assertNotEqual(payment.state, "draft")

    def test_inbound_converted_to_bundle_drops_old_move(self):
        payment, old_move = self._post_then_convert_to_bundle("inbound")
        self.assertFalse(payment.move_id)
        self.assertFalse(old_move.exists())
        self.assertNotEqual(payment.state, "draft")
