from unittest import SkipTest

from odoo import Command, fields
from odoo.tests import Form, common, tagged


@tagged("post_install", "-at_install")
class TestPaymentCurrencyRoundTrip(common.TransactionCase):
    """Switching the payment journal to another currency and back to the company
    currency must keep the amount the payment had before the round trip."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.today = fields.Date.context_today(cls.env.user)
        cls.eur = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "EUR")])
        cls.eur.active = True
        if cls.eur == cls.company.currency_id:
            raise SkipTest("Test requires a company currency other than EUR")
        # An odd rate so that converting back and forth does not give a round number
        cls.env["res.currency.rate"].create(
            {
                "name": cls.today,
                "inverse_company_rate": 1450.37,
                "currency_id": cls.eur.id,
                "company_id": cls.company.id,
            }
        )
        cls.company_journal = cls.env["account.journal"].create(
            {"name": "Cash company currency", "type": "cash", "code": "CCC", "company_id": cls.company.id}
        )
        cls.eur_journal = cls.env["account.journal"].create(
            {
                "name": "Cash EUR",
                "type": "cash",
                "code": "CEUR",
                "currency_id": cls.eur.id,
                "company_id": cls.company.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Round Trip Partner"})
        cls.invoice = cls.env["account.move"].create(
            {
                "partner_id": cls.partner.id,
                "move_type": "out_invoice",
                "invoice_date": cls.today,
                "company_id": cls.company.id,
                "currency_id": cls.company.currency_id.id,
                "invoice_line_ids": [
                    Command.create({"name": "Service", "quantity": 1, "price_unit": 67920930.0, "tax_ids": []}),
                ],
            }
        )
        cls.invoice.action_post()

    def _payment_form(self):
        action_context = self.invoice.action_register_payment()["context"]
        payment_form = Form(self.env["account.payment"].with_context(**action_context))
        payment_form.journal_id = self.company_journal
        return payment_form

    def _round_trip(self, payment_form):
        payment_form.journal_id = self.eur_journal
        payment_form.journal_id = self.company_journal

    def test_round_trip_keeps_default_amount(self):
        """Without touching the amount, the round trip gives back the invoice total
        exactly, with no rounding drift (ticket 120946)."""
        payment_form = self._payment_form()
        self.assertEqual(payment_form.amount, self.invoice.amount_total)
        self._round_trip(payment_form)
        self.assertEqual(payment_form.amount, self.invoice.amount_total)

    def test_round_trip_keeps_amount_changed_by_the_user(self):
        """An amount changed before the round trip (a partial payment, or the total
        net of withholdings) is not replaced by the invoice total (ticket 133697)."""
        payment_form = self._payment_form()
        payment_form.amount = 66744810.0
        self._round_trip(payment_form)
        self.assertAlmostEqual(payment_form.amount, 66744810.0, places=2)
