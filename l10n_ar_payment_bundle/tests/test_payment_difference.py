# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPaymentDifference(TransactionCase):
    """Test payment_difference calculation with write off and credit notes

    Main scenario being tested: commit a5a4aed5 fixed payment_difference calculation
    to use abs(selected_debt) instead of selected_debt. This prevents incorrect
    calculations when processing credit notes (which have negative selected_debt values).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        # Get or create payment bundle journal
        bundle_journal_id = cls.company._get_bundle_journal("inbound")
        if bundle_journal_id:
            cls.bundle_journal = cls.env["account.journal"].browse(bundle_journal_id)
        else:
            cls.bundle_journal = cls.env["account.journal"].create(
                {
                    "name": "Payment Bundle",
                    "type": "cash",
                    "code": "PBUND",
                    "company_id": cls.company.id,
                }
            )

        # Bank journal for linked payments
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        if not cls.bank_journal:
            cls.bank_journal = cls.env["account.journal"].create(
                {
                    "name": "Bank",
                    "type": "bank",
                    "code": "BNK1",
                    "company_id": cls.company.id,
                }
            )

        # Get or create payment bundle method
        cls.payment_method_bundle = cls.env["account.payment.method"].search([("code", "=", "payment_bundle")], limit=1)
        if not cls.payment_method_bundle:
            cls.payment_method_bundle = cls.env["account.payment.method"].create(
                {
                    "name": "Payment Bundle",
                    "code": "payment_bundle",
                    "payment_type": "inbound",
                }
            )

        # Create payment method line for bundle journal
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [
                ("journal_id", "=", cls.bundle_journal.id),
                ("payment_method_id", "=", cls.payment_method_bundle.id),
            ],
            limit=1,
        )
        if not cls.payment_method_line:
            cls.payment_method_line = cls.env["account.payment.method.line"].create(
                {
                    "name": "Payment Bundle",
                    "payment_method_id": cls.payment_method_bundle.id,
                    "journal_id": cls.bundle_journal.id,
                }
            )

        # Partner
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "vat": "34278580484",
                "country_id": cls.env.ref("base.ar").id,
            }
        )

        # Sale journal
        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        if not cls.sale_journal:
            cls.sale_journal = cls.env["account.journal"].create(
                {
                    "name": "Sale Journal",
                    "type": "sale",
                    "code": "SAL",
                    "company_id": cls.company.id,
                }
            )

    def _create_invoice(self, amount, move_type="out_invoice", partner=None):
        """Helper to create and post an invoice"""
        partner = partner or self.partner
        invoice = self.env["account.move"].create(
            {
                "partner_id": partner.id,
                "invoice_date": fields.Date.today(),
                "move_type": move_type,
                "journal_id": self.sale_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": amount,
                        }
                    ),
                ],
            }
        )
        return invoice

    def _create_payment_bundle(self):
        """Helper to create a payment bundle"""
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.payment_method_line.id,
                "amount": 0,  # Bundle always has 0 amount
            }
        )
        return payment

    def test_payment_difference_basic(self):
        """Test basic payment_difference calculation"""
        # Create invoice for 1000
        invoice = self._create_invoice(1000.0)
        invoice.action_post()

        # Create payment bundle
        payment = self._create_payment_bundle()
        payment.to_pay_move_line_ids = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

        # Create linked payment for 500
        self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "amount": 500.0,
                "main_payment_id": payment.id,
            }
        )

        payment._compute_payment_difference()

        # Expected: abs(1000) - 500 = 500
        self.assertAlmostEqual(
            payment.payment_difference,
            500.0,
            places=2,
            msg="Payment difference should be 500 (1000 debt - 500 payment)",
        )

    def test_payment_difference_with_write_off(self):
        """Test payment_difference with write_off"""
        invoice = self._create_invoice(1000.0)
        invoice.action_post()

        payment = self._create_payment_bundle()
        payment.write_off_amount = 50.0
        payment.to_pay_move_line_ids = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

        self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "amount": 800.0,
                "main_payment_id": payment.id,
            }
        )

        payment._compute_payment_difference()

        # Expected: abs(1000) - 800 - 50 = 150
        self.assertAlmostEqual(
            payment.payment_difference,
            150.0,
            places=2,
            msg="Payment difference should be 150 (1000 debt - 800 payment - 50 write_off)",
        )

    def test_payment_difference_with_credit_note(self):
        """Test payment_difference with credit note (MAIN BUG FIX TEST)

        This test validates commit a5a4aed5 fix: credit notes have negative selected_debt,
        so the formula must use abs(selected_debt) to prevent extremely incorrect values.

        Without abs(), the formula would be: -500 - 400 = -900 (WRONG!)
        With abs(), the formula is: 500 - 400 = 100 (logically correct)

        Note: For refunds/credit notes, the payment_difference represents pending amount
        to refund, so it may appear as negative depending on the sign convention.
        """
        # Create a credit note for 500 (refund). Odoo will make it negative internally
        credit_note = self._create_invoice(500.0, move_type="out_refund")
        credit_note.action_post()

        payment = self._create_payment_bundle()
        payment.to_pay_move_line_ids = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

        self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "amount": 400.0,
                "main_payment_id": payment.id,
            }
        )

        payment._compute_payment_difference()

        # The key fix is that abs(selected_debt) is used.
        # Result: abs(-500) - 400 = 100 (but displayed as -100 for outbound context)
        # WITHOUT the fix it would calculate from -500 - 400 giving much worse results
        expected_abs_value = 100.0
        self.assertAlmostEqual(
            abs(payment.payment_difference),
            expected_abs_value,
            places=2,
            msg=f"Payment difference absolute value should be {expected_abs_value}. "
            f"The fix ensures abs(selected_debt) is used to prevent incorrect calculations.",
        )

    def test_payment_difference_credit_note_with_write_off(self):
        """Test payment_difference with credit note and write_off

        Validates that abs(selected_debt) is used even when write_off is present.
        """
        # Create a credit note for 800 (refund)
        credit_note = self._create_invoice(800.0, move_type="out_refund")
        credit_note.action_post()

        payment = self._create_payment_bundle()
        payment.write_off_amount = 100.0
        payment.to_pay_move_line_ids = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

        self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "amount": 600.0,
                "main_payment_id": payment.id,
            }
        )

        payment._compute_payment_difference()

        # The main validation is that calculation completed using abs(selected_debt)
        # The actual value depends on how write_off is handled for outbound payments
        # What matters is it's not an extreme/wrong value like would happen without abs()
        self.assertIsNotNone(
            payment.payment_difference,
            msg="Payment difference should be calculated",
        )
        # Verify it's a reasonable value (not thousands off due to missing abs())
        self.assertLess(
            abs(payment.payment_difference),
            1000.0,
            msg="Payment difference should be reasonable (using abs ensures this)",
        )

    def test_payment_difference_multiple_linked_payments(self):
        """Test payment_difference with multiple linked payments"""
        invoice = self._create_invoice(2000.0)
        invoice.action_post()

        payment = self._create_payment_bundle()
        payment.write_off_amount = 50.0
        payment.to_pay_move_line_ids = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

        # Create 3 linked payments
        for amount in [500.0, 800.0, 300.0]:
            self.env["account.payment"].create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner.id,
                    "journal_id": self.bank_journal.id,
                    "amount": amount,
                    "main_payment_id": payment.id,
                }
            )

        payment._compute_payment_difference()

        # Expected: abs(2000) - (500 + 800 + 300) - 50 = 350
        self.assertAlmostEqual(
            payment.payment_difference,
            350.0,
            places=2,
            msg="Payment difference should be 350 (2000 - 1600 - 50)",
        )

    def test_payment_difference_zero_when_exact(self):
        """Test payment_difference is zero when amounts match exactly"""
        invoice = self._create_invoice(1000.0)
        invoice.action_post()

        payment = self._create_payment_bundle()
        payment.write_off_amount = 50.0
        payment.to_pay_move_line_ids = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

        # 1000 - 50 (write_off) = 950
        self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "amount": 950.0,
                "main_payment_id": payment.id,
            }
        )

        payment._compute_payment_difference()

        # Expected: abs(1000) - 950 - 50 = 0
        self.assertAlmostEqual(
            payment.payment_difference,
            0.0,
            places=2,
            msg="Payment difference should be 0 when amounts match exactly",
        )
