##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from datetime import timedelta

from odoo import Command
from odoo.addons.account_payment_early_discount.tests.common import EarlyDiscountCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestBundleEarlyDiscount(EarlyDiscountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        bundle_journal_id = cls.company._get_bundle_journal("inbound")
        if bundle_journal_id:
            cls.bundle_journal = cls.env["account.journal"].browse(bundle_journal_id)
        else:
            cls.bundle_journal = cls.env["account.journal"].create(
                {"name": "Payment Bundle ED", "type": "cash", "code": "PBUED"}
            )
        cls.bundle_method_line = cls.bundle_journal.inbound_payment_method_line_ids.filtered(
            lambda x: x.code == "payment_bundle"
        )[:1]
        # with account_multi_store, reconcile() only accepts journals of the same store as the debt
        if "store_id" in cls.env["account.journal"]._fields:
            (cls.bundle_journal | cls.bank_journal).store_id = cls.sale_journal.store_id

    def _create_bundle(self, invoice, linked_date):
        """Main payment dated today on the invoice debt, with a linked payment still without amount."""
        main = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.bundle_method_line.id,
                "date": self.today,
                "amount": 0,
                "to_pay_move_line_ids": [
                    Command.set(invoice.line_ids.filtered(lambda line: line.display_type == "payment_term").ids)
                ],
            }
        )
        linked = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "date": linked_date,
                "amount": 0,
                "main_payment_id": main.id,
            }
        )
        return main, linked

    def _early_discount_credit_notes(self, invoice):
        return invoice.reversal_move_ids.filtered("is_early_discount")

    def test_bundle_applies_discount_once_from_main(self):
        """The main payment decides and applies the early discount with its own date: the linked payment has no
        discount of its own, even dated after the discount period, and suggests the amount with discount. While the
        bundle is built, the main payment shows the discount it gets if it pays all the debt, so the main and the
        linked payment show the same difference."""
        invoice = self._create_invoice(self.today)
        discounted = self._discounted_total(invoice)
        main, linked = self._create_bundle(invoice, self.today + timedelta(days=11))

        with self.subTest("the linked payment has no discount of its own"):
            self.assertFalse(linked.early_discount_available)
            self.assertTrue(main.early_discount_available)

        with self.subTest("partly paid, the main and the linked payment show the same difference, with the discount"):
            self.assertAlmostEqual(main.early_discount_difference, discounted, places=2)
            self.assertAlmostEqual(linked.payment_difference, discounted, places=2)
            linked.amount = discounted / 3
            self.assertAlmostEqual(main.early_discount_difference, linked.payment_difference, places=2)
            self.assertAlmostEqual(linked.payment_difference, discounted - linked.amount, places=2)
            self.assertFalse(main.bundle_early_discount_applied)

        with self.subTest("once the linked payments pay the discounted invoice, the main shows the discount"):
            linked.action_adjust_amount_for_difference()
            self.assertAlmostEqual(linked.amount, discounted, places=2)
            self.assertAlmostEqual(main.bundle_early_discount_applied, invoice.amount_total - discounted, places=2)
            self.assertTrue(main.currency_id.is_zero(main.early_discount_difference))

        with self.subTest("posting the bundle creates a single credit note, from the main payment"):
            main.action_post()
            credit_notes = self._early_discount_credit_notes(invoice)
            self.assertEqual(len(credit_notes), 1)
            self.assertEqual(credit_notes.early_discount_payment_id, main)
            self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
            self.assertTrue(invoice.currency_id.is_zero(main.unmatched_amount))
            self.assertEqual(main.amount, 0)

    def test_bundle_exclude_on_main(self):
        """Excluding and recalculating on the main payment only turns the discount off and on: the main amount stays
        zero and the linked payment follows it. With the discount excluded, the linked payment does not create the
        credit note even within the discount period. A date change on the main runs the same code as these buttons.
        """
        invoice = self._create_invoice(self.today)
        discounted = self._discounted_total(invoice)
        main, linked = self._create_bundle(invoice, self.today)

        with self.subTest("excluding on the main payment keeps its amount at zero"):
            main.action_early_discount_exclude()
            self.assertFalse(main.early_discount_apply)
            self.assertEqual(main.amount, 0)

        with self.subTest("the linked payment shows the full difference again"):
            self.assertAlmostEqual(linked.payment_difference, invoice.amount_total, places=2)

        with self.subTest("recalculating applies the discount on the linked payment again"):
            main.action_early_discount_recalculate()
            self.assertEqual(main.amount, 0)
            self.assertAlmostEqual(linked.payment_difference, discounted, places=2)
            main.action_early_discount_exclude()

        with self.subTest("posting with the discount excluded does not create a credit note"):
            linked.action_adjust_amount_for_difference()
            main.action_post()
            self.assertFalse(self._early_discount_credit_notes(invoice))
            self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_bundle_returned_check_warns_on_main(self):
        """The credit note belongs to the main payment, so a check returned from a linked payment warns there."""
        if "l10n_latam_new_check_ids" not in self.env["account.payment"]._fields:
            self.skipTest("Checks not installed")
        invoice = self._create_invoice(self.today)
        main, linked = self._create_bundle(invoice, self.today)
        linked.action_adjust_amount_for_difference()
        main.action_post()
        credit_note = self._early_discount_credit_notes(invoice)
        check = self.env["l10n_latam.check"].create(
            {"payment_id": linked.id, "name": "00000001", "payment_date": self.today, "amount": linked.amount}
        )
        return_method = self.env.ref("l10n_latam_check.account_payment_method_return_third_party_checks")
        method_lines = self.bank_journal.outbound_payment_method_line_ids
        return_line = method_lines.filtered(lambda line: line.payment_method_id == return_method)[:1]
        if not return_line:
            return_line = method_lines.create(
                {"journal_id": self.bank_journal.id, "payment_method_id": return_method.id}
            )
        if not return_line.payment_account_id:
            return_line.payment_account_id = self.outstanding_account
        return_payment = self.env["account.payment"].create(
            {
                "journal_id": self.bank_journal.id,
                "partner_id": self.partner.id,
                "partner_type": "customer",
                "payment_type": "outbound",
                "amount": linked.amount,
                "payment_method_line_id": return_line.id,
            }
        )
        check.operation_ids = return_payment
        return_payment.state = "in_process"
        main.invalidate_recordset(["early_discount_warning_credit_note_ids"])
        self.assertEqual(main.early_discount_warning_credit_note_ids, credit_note)

    def test_bundle_partly_covered_shows_applied_discount(self):
        """With two discounted invoices and the linked payments paying only the first one, the main payment shows the
        discount applied if posted now, the one of the first invoice, and its difference keeps the discount of both
        to pay the second invoice with discount too."""
        first = self._create_invoice(self.today, lines=[{"name": "Small", "quantity": 1, "price_unit": 500}])
        second = self._create_invoice(self.today)
        main, linked = self._create_bundle(first | second, self.today)
        # with the same due date, the smaller invoice is paid first
        linked.amount = self._discounted_total(first)

        self.assertAlmostEqual(
            main.bundle_early_discount_applied, first.amount_total - self._discounted_total(first), places=2
        )
        self.assertAlmostEqual(main.early_discount_difference, self._discounted_total(second), places=2)
        self.assertAlmostEqual(linked.payment_difference, self._discounted_total(second), places=2)
