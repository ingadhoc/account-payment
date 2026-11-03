##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from datetime import timedelta

from odoo import Command
from odoo.tests import tagged

from .common import EarlyDiscountCommon


@tagged("post_install", "-at_install")
class TestEarlyDiscountEligibility(EarlyDiscountCommon):
    def test_full_payment_within_period(self):
        invoice = self._create_invoice(self.today)
        discounted = self._discounted_total(invoice)
        self.assertTrue(invoice._is_early_discount_eligible(self.today, discounted))
        self.assertFalse(invoice._is_early_discount_eligible(self.today, discounted - 1))

    def test_payment_after_period(self):
        invoice = self._create_invoice(self.today - timedelta(days=11))
        self.assertFalse(invoice._is_early_discount_eligible(self.today, invoice.amount_total))

    def test_partial_payments_within_period(self):
        invoice = self._create_invoice(self.today)
        discounted = self._discounted_total(invoice)
        self._pay(invoice, discounted / 2, self.today)
        self.assertTrue(invoice._is_early_discount_eligible(self.today, discounted / 2))
        self.assertFalse(invoice._is_early_discount_eligible(self.today, discounted / 2 - 1))

    def test_previous_payment_after_period(self):
        invoice = self._create_invoice(self.today - timedelta(days=11))
        discount_date = self.today - timedelta(days=1)
        discounted = self._discounted_total(invoice)
        self._pay(invoice, discounted / 2, self.today)
        self.assertFalse(invoice._is_early_discount_eligible(discount_date, discounted / 2))

    def test_previous_credit_note_after_period(self):
        # a regular credit note reconciled after the period is not a payment and keeps the discount
        invoice = self._create_invoice(self.today - timedelta(days=11))
        discount_date = self.today - timedelta(days=1)
        credit_note = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": self.today,
                "reversed_entry_id": invoice.id,
                "invoice_line_ids": [Command.create({"name": "Refund", "quantity": 1, "price_unit": 100})],
            }
        )
        credit_note.action_post()
        (credit_note + invoice).line_ids.filtered(lambda line: line.display_type == "payment_term").reconcile()
        required = invoice.amount_residual - invoice._get_early_discount_amount()
        self.assertTrue(invoice._is_early_discount_eligible(discount_date, required))
        self.assertFalse(invoice._is_early_discount_eligible(discount_date, required - 1))

    def test_existing_early_discount_credit_note(self):
        invoice = self._create_invoice(self.today)
        discounted = self._discounted_total(invoice)
        credit_note = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner.id,
                "journal_id": self.sale_journal.id,
                "reversed_entry_id": invoice.id,
                "is_early_discount": True,
                "invoice_line_ids": [Command.create({"name": "Discount", "quantity": 1, "price_unit": 50})],
            }
        )
        self.assertFalse(invoice._is_early_discount_eligible(self.today, discounted))
        credit_note.button_cancel()
        self.assertTrue(invoice._is_early_discount_eligible(self.today, discounted))

    def test_company_without_payment_pro(self):
        invoice = self._create_invoice(self.today)
        self.company.use_payment_pro = False
        self.assertFalse(invoice._is_early_discount_eligible(self.today, invoice.amount_total))

    def test_debt_line_discount_available(self):
        invoice = self._create_invoice(self.today)
        term_line = invoice.line_ids.filtered(lambda line: line.display_type == "payment_term")
        self.assertTrue(term_line.early_discount_available)
        expired = self._create_invoice(self.today - timedelta(days=11))
        self.assertFalse(
            expired.line_ids.filtered(lambda line: line.display_type == "payment_term").early_discount_available
        )
