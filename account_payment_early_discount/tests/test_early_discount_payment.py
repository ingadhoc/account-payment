##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from datetime import timedelta
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
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

    def test_suggested_amount_with_taxes_settles_invoice(self):
        # with fixed taxes and lines rounded one by one, the suggested amount and the credit note settle the invoice
        tax = self.env["account.tax"]
        vat_21 = tax.create({"name": "VAT 21% ED", "amount": 21, "type_tax_use": "sale"})
        vat_105 = tax.create({"name": "VAT 10.5% ED", "amount": 10.5, "type_tax_use": "sale"})
        perception = tax.create({"name": "Perception 3% ED", "amount": 3, "type_tax_use": "sale"})
        fixed = tax.create({"name": "Fixed 10 ED", "amount_type": "fixed", "amount": 10, "type_tax_use": "sale"})
        invoice = self._create_invoice(
            self.today,
            lines=[
                {"name": "A", "quantity": 1, "price_unit": 33.33, "tax_ids": [Command.set((vat_21 + fixed).ids)]},
                {"name": "B", "quantity": 1, "price_unit": 33.33, "tax_ids": [Command.set(vat_105.ids)]},
                {"name": "C", "quantity": 1, "price_unit": 33.33, "tax_ids": [Command.set((vat_21 + perception).ids)]},
            ],
        )
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
        payment = form.record
        payment.action_post()
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(credit_note.state, "posted")
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
        self.assertTrue(credit_note.currency_id.is_zero(credit_note.amount_residual))

    def test_discount_without_loss_account(self):
        self.company.account_journal_early_pay_discount_loss_account_id = False
        invoice = self._create_invoice(self.today)
        with self.assertRaisesRegex(UserError, "Early Discount Loss"):
            self._post_payment(invoice, 950)

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

    def test_linked_regular_credit_note(self):
        invoice = self._create_invoice(self.today)
        regular = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": self.today,
                "reversed_entry_id": invoice.id,
                "invoice_line_ids": [Command.create({"name": "Refund", "quantity": 1, "price_unit": 100})],
            }
        )
        regular.action_post()
        (regular + invoice).line_ids.filtered(lambda line: line.display_type == "payment_term").reconcile()
        # 900 owed, 5% discount on it
        self._post_payment(invoice, 855)
        self.assertAlmostEqual(self._early_discount_credit_note(invoice).amount_total, 45)
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

    def test_suggested_amount_foreign_currency_rate_of_payment_date(self):
        eur = self.env.ref("base.EUR")
        foreign = eur if self.company.currency_id != eur else self.env.ref("base.USD")
        foreign.active = True
        self.env["res.currency.rate"].create(
            [
                {"currency_id": foreign.id, "name": self.today - timedelta(days=30), "inverse_company_rate": 1000},
                {"currency_id": foreign.id, "name": self.today, "inverse_company_rate": 1100},
            ]
        )
        invoice = self._create_invoice(self.today - timedelta(days=5), currency_id=foreign.id)
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
            self.assertAlmostEqual(form.amount, 1045000)
            self.assertAlmostEqual(form.early_discount_amount, 50)
            self.assertAlmostEqual(form.early_discount_difference, 0)
        form.record.action_post()
        self.assertAlmostEqual(self._early_discount_credit_note(invoice).amount_total, 50)
        self.assertTrue(foreign.is_zero(invoice.amount_residual))

    def test_suggested_amount_foreign_currency_follows_date(self):
        # the rate changes with the payment date, so the suggested amount in company currency changes too
        eur = self.env.ref("base.EUR")
        foreign = eur if self.company.currency_id != eur else self.env.ref("base.USD")
        foreign.active = True
        self.env["res.currency.rate"].create(
            [
                {"currency_id": foreign.id, "name": self.today - timedelta(days=30), "inverse_company_rate": 1000},
                {"currency_id": foreign.id, "name": self.today - timedelta(days=3), "inverse_company_rate": 1050},
                {"currency_id": foreign.id, "name": self.today, "inverse_company_rate": 1100},
            ]
        )
        invoice = self._create_invoice(self.today - timedelta(days=5), currency_id=foreign.id)
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
            self.assertAlmostEqual(form.amount, 1045000)
            form.date = self.today - timedelta(days=3)
            self.assertAlmostEqual(form.amount, 997500)
            self.assertAlmostEqual(form.early_discount_difference, 0)
            form.date = self.today
            self.assertAlmostEqual(form.amount, 1045000)
            # an amount set by the user is kept
            form.amount = 1000000
            form.date = self.today - timedelta(days=3)
            self.assertAlmostEqual(form.amount, 1000000)
            form.amount = 997500
        form.record.action_post()
        self.assertAlmostEqual(self._early_discount_credit_note(invoice).amount_total, 50)
        self.assertTrue(foreign.is_zero(invoice.amount_residual))

    def test_adjust_difference_after_discount(self):
        invoice = self._create_invoice(self.today)
        payment = self._draft_payment(invoice, 960)
        self.assertAlmostEqual(payment.early_discount_difference, -10)
        payment.action_adjust_amount_for_difference()
        self.assertAlmostEqual(payment.amount, 950)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        # nothing left to adjust: the discount is kept
        payment.action_adjust_amount_for_difference()
        payment.action_adjust_writeoff_for_difference()
        self.assertAlmostEqual(payment.amount, 950)
        self.assertFalse(payment.write_off_amount)
        payment.amount = 955
        payment.action_adjust_writeoff_for_difference()
        self.assertAlmostEqual(payment.write_off_amount, -5)
        self.assertAlmostEqual(payment.early_discount_amount, 50)

    def test_exclude_discount(self):
        invoice = self._create_invoice(self.today)
        context = invoice.action_register_payment()["context"]
        with Form(self.env["account.payment"].with_context(**context)) as form:
            form.journal_id = self.bank_journal
            self.assertAlmostEqual(form.amount, 950)
        payment = form.record
        payment.action_early_discount_exclude()
        self.assertAlmostEqual(payment.amount, 1000)
        self.assertFalse(payment.early_discount_amount)
        self.assertTrue(payment.early_discount_available)
        payment.action_early_discount_recalculate()
        self.assertAlmostEqual(payment.amount, 950)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        payment.action_early_discount_exclude()
        payment.action_post()
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_exclude_discount_only_on_that_payment(self):
        # the next payment of the invoice gets the discount again
        invoice = self._create_invoice(self.today)
        payment = self._draft_payment(invoice, 950, early_discount_apply=False)
        payment.action_post()
        self.assertFalse(self._early_discount_credit_note(invoice))
        self.assertAlmostEqual(invoice.amount_residual, 50)
        next_payment = self._draft_payment(invoice, 10)
        self.assertTrue(next_payment.early_discount_apply)
        self.assertAlmostEqual(next_payment.early_discount_amount, 50)

    def test_draft_payment_discount_depends_on_amount(self):
        invoice = self._create_invoice(self.today)
        payment = self._draft_payment(invoice, 950)
        self.assertAlmostEqual(payment.payment_difference, 50)
        self.assertAlmostEqual(payment.early_discount_amount, 50)
        self.assertAlmostEqual(payment.early_discount_difference, 0)
        payment.amount = 949
        self.assertFalse(payment.early_discount_amount)
        self.assertAlmostEqual(payment.early_discount_difference, 51)

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

    def test_cancelled_payment_warns_posted_credit_note(self):
        invoice = self._create_invoice(self.today)
        payment = self._post_payment(invoice, 950)
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(credit_note.early_discount_payment_id, payment)
        self.assertFalse(payment.early_discount_warning_credit_note_ids)
        payment.action_draft()
        payment.action_cancel()
        self.assertEqual(payment.early_discount_warning_credit_note_ids, credit_note)

    def test_returned_check_warns_posted_credit_note(self):
        if "l10n_latam_new_check_ids" not in self.env["account.payment"]._fields:
            self.skipTest("Checks not installed")
        invoice = self._create_invoice(self.today)
        payment = self._post_payment(invoice, 950)
        credit_note = self._early_discount_credit_note(invoice)
        check = self.env["l10n_latam.check"].create(
            {"payment_id": payment.id, "name": "00000001", "payment_date": self.today, "amount": 950}
        )
        self.assertFalse(payment.early_discount_warning_credit_note_ids)
        # the customer debit that the check rejection posts
        return_method = self.env.ref("l10n_latam_check.account_payment_method_return_third_party_checks")
        method_lines = self.bank_journal.outbound_payment_method_line_ids
        return_line = method_lines.filtered(lambda line: line.payment_method_id == return_method)[:1]
        if not return_line:
            return_line = method_lines.create(
                {"journal_id": self.bank_journal.id, "payment_method_id": return_method.id}
            )
        # check payment methods need an outstanding account
        if not return_line.payment_account_id:
            return_line.payment_account_id = self.outstanding_account
        return_payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.partner.id,
                "partner_type": "customer",
                "payment_type": "outbound",
                "amount": 950,
                "payment_method_line_id": return_line.id,
            }
        )
        check.operation_ids = return_payment
        payment.invalidate_recordset(["early_discount_warning_credit_note_ids"])
        self.assertFalse(payment.early_discount_warning_credit_note_ids, "a draft return does not warn")
        return_payment.state = "in_process"
        payment.invalidate_recordset(["early_discount_warning_credit_note_ids"])
        self.assertEqual(payment.early_discount_warning_credit_note_ids, credit_note)

    def test_credit_note_left_in_draft(self):
        # a customization that does not post the credit note must not block the payment
        with patch.object(type(self.env["account.move"]), "_post_early_discount_credit_note", lambda self: None):
            invoice = self._create_invoice(self.today)
            payment = self._post_payment(invoice, 950)
        credit_note = self._early_discount_credit_note(invoice)
        self.assertEqual(credit_note.state, "draft")
        self.assertNotEqual(payment.state, "draft")
        self.assertAlmostEqual(invoice.amount_residual, 50)
