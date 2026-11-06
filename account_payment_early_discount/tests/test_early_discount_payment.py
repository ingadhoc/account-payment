##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from datetime import timedelta
from unittest.mock import patch

from odoo.tests import Form, tagged

from .common import EarlyDiscountCommon


@tagged("post_install", "-at_install")
class TestEarlyDiscountPayment(EarlyDiscountCommon):
    def _post_payment(self, invoices, amount):
        context = invoices.action_register_payment()["context"]
        payment = (
            self.env["account.payment"]
            .with_context(**context)
            .create({"journal_id": self.bank_journal.id, "amount": amount, "date": self.today})
        )
        payment.action_post()
        return payment

    def _create_invoice_without_discount(self, due_days, amount=500):
        """Invoice without early discount, due in ``due_days``."""
        return self._create_invoice(
            self.today,
            lines=[{"name": "Other", "quantity": 1, "price_unit": amount}],
            invoice_payment_term_id=False,
            invoice_date_due=self.today + timedelta(days=due_days),
        )

    def _early_discount_credit_note(self, invoice):
        return invoice.reversal_move_ids.filtered("is_early_discount")

    def test_single_invoice_discounted_amount(self):
        invoice = self._create_invoice(self.today)
        self._post_payment(invoice, 950)
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(credit_note.state, "posted")
        self.assertAlmostEqual(credit_note.amount_total, 50)
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_single_invoice_not_enough(self):
        invoice = self._create_invoice(self.today)
        self._post_payment(invoice, 949)
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertAlmostEqual(invoice.amount_residual, 51)

    def test_partial_payments_then_completing_payment(self):
        invoice = self._create_invoice(self.today)
        self._post_payment(invoice, 500)
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertAlmostEqual(invoice.amount_residual, 500)
        # 450 completes the discounted total of 950
        self._post_payment(invoice, 450)
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(len(credit_note), 1)
        self.assertAlmostEqual(credit_note.amount_total, 50)
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_partial_payments_not_completing(self):
        invoice = self._create_invoice(self.today)
        self._post_payment(invoice, 500)
        self._post_payment(invoice, 449)
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertAlmostEqual(invoice.amount_residual, 51)

    def test_discounted_invoice_due_first(self):
        # the payment covers the discounted invoice and the surplus goes to the other one
        invoice = self._create_invoice(self.today)
        other = self._create_invoice_without_discount(due_days=60)
        self._post_payment(invoice + other, 970)
        self.assertTrue(self._early_discount_credit_note(invoice))
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
        self.assertAlmostEqual(other.amount_residual, 480)

    def test_other_invoice_due_first(self):
        # the invoice due first takes the payment and the discounted one is not fully paid
        invoice = self._create_invoice(self.today)
        other = self._create_invoice_without_discount(due_days=0)
        self._post_payment(invoice + other, 970)
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertTrue(other.currency_id.is_zero(other.amount_residual))
        self.assertAlmostEqual(invoice.amount_residual, 530)

    def test_same_due_date_smaller_first(self):
        # with the same due date the reconciliation pays the smaller amount first, as Odoo does
        invoice = self._create_invoice(self.today)
        other = self._create_invoice_without_discount(due_days=30)
        self._post_payment(invoice + other, 970)
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertTrue(other.currency_id.is_zero(other.amount_residual))
        self.assertAlmostEqual(invoice.amount_residual, 530)

    def test_same_due_date_discounted_smaller(self):
        other = self._create_invoice_without_discount(due_days=30, amount=1500)
        invoice = self._create_invoice(self.today)
        self._post_payment(invoice + other, 970)
        self.assertTrue(self._early_discount_credit_note(invoice))
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
        self.assertAlmostEqual(other.amount_residual, 1480)

    def _draft_payment(self, invoices, amount, **vals):
        context = invoices.action_register_payment()["context"]
        return (
            self.env["account.payment"]
            .with_context(**context)
            .create({"journal_id": self.bank_journal.id, "amount": amount, "date": self.today, **vals})
        )

    def test_suggested_amount_with_discount(self):
        invoice = self._create_invoice(self.today)
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
        payment = form.record
        self.assertAlmostEqual(payment.amount, 950)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        self.assertAlmostEqual(payment.early_discount_difference, 0)

    def test_suggested_amount_when_adding_debt(self):
        invoice = self._create_invoice(self.today)
        other = self._create_invoice_without_discount(due_days=60)
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
            form.to_pay_move_line_ids.add(other.line_ids.filtered(lambda line: line.display_type == "payment_term"))
        payment = form.record
        self.assertAlmostEqual(payment.amount, 1450)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        self.assertAlmostEqual(payment.early_discount_difference, 0)

    def test_suggested_amount_without_discount(self):
        invoice = self._create_invoice(self.today - timedelta(days=11))
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
        payment = form.record
        self.assertAlmostEqual(payment.amount, 1000)
        self.assertFalse(payment.early_discount_amount)

    def test_suggested_amount_follows_date(self):
        # discount period ended two days ago
        invoice = self._create_invoice(self.today - timedelta(days=12))
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
            self.assertAlmostEqual(form.amount, 1000)
            form.date = self.today - timedelta(days=3)
            self.assertAlmostEqual(form.amount, 950)
            form.date = self.today
            self.assertAlmostEqual(form.amount, 1000)
            # an amount set by the user is kept
            form.amount = 990
            form.date = self.today - timedelta(days=3)
            self.assertAlmostEqual(form.amount, 990)

    def test_suggested_amount_foreign_currency(self):
        eur = self.env.ref("base.EUR")
        foreign = eur if self.company.currency_id != eur else self.env.ref("base.USD")
        foreign.active = True
        self.env["res.currency.rate"].create(
            {"currency_id": foreign.id, "name": self.today - timedelta(days=30), "inverse_company_rate": 1000}
        )
        invoice = self._create_invoice(self.today, currency_id=foreign.id)
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
            self.assertAlmostEqual(form.amount, 950000)
            self.assertAlmostEqual(form.early_discount_amount, 50)
            self.assertAlmostEqual(form.early_discount_difference, 0)
        form.record.action_post()
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(credit_note.currency_id, foreign)
        self.assertAlmostEqual(credit_note.amount_total, 50)
        self.assertTrue(foreign.is_zero(invoice.amount_residual))

    def test_draft_payment_discount_depends_on_amount(self):
        invoice = self._create_invoice(self.today)
        payment = self._draft_payment(invoice, 950)
        self.assertAlmostEqual(payment.payment_difference, 50)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        self.assertAlmostEqual(payment.early_discount_difference, 0)
        payment.amount = 949
        self.assertFalse(payment.early_discount_amount)
        self.assertAlmostEqual(payment.early_discount_difference, 51)

    def test_write_off_warning(self):
        write_off_account = self.env["account.account"].search(
            [("company_ids", "=", self.company.id), ("account_type", "=", "expense")], limit=1
        )
        write_off_type = self.env["account.write_off.type"].create(
            {"name": "Write-off ED", "account_id": write_off_account.id}
        )
        invoice = self._create_invoice(self.today)
        # the write-off covers the discount: the payment exceeds the debt
        payment = self._draft_payment(invoice, 950, write_off_amount=50, write_off_type_id=write_off_type.id)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        self.assertTrue(payment.early_discount_write_off_warning)
        # a small write-off to complete the discounted amount is fine
        payment.write({"amount": 948, "write_off_amount": 2})
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        self.assertFalse(payment.early_discount_write_off_warning)

    def test_without_payment_pro_uses_native_discount(self):
        self.company.use_payment_pro = False
        invoice = self._create_invoice(self.today)
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create({"journal_id": self.bank_journal.id, "amount": 950, "payment_date": self.today})
        )
        wizard.action_create_payments()
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_credit_note_left_in_draft(self):
        # a customization that does not post the credit note must not block the payment
        with patch.object(type(self.env["account.move"]), "_post_early_discount_credit_note", lambda self: None):
            invoice = self._create_invoice(self.today)
            payment = self._post_payment(invoice, 950)
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(credit_note.state, "draft")
        self.assertNotEqual(payment.state, "draft")
        self.assertAlmostEqual(invoice.amount_residual, 50)
