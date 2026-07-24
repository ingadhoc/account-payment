import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import ReceiptbookCommon


@tagged("post_install", "-at_install")
class TestAccountPaymentProReceiptbookUnitTest(ReceiptbookCommon):
    def test_create_payment_with_receiptbook(self):
        invoice = self._create_invoice()
        # Próximo número de la secuencia del receiptbook antes de postear
        # (robusto al orden de ejecución: la secuencia estándar no rollbackea)
        expected_name = "%s %s%s" % (
            self.receiptbook.document_type_id.doc_code_prefix,
            self.receiptbook.prefix,
            str(self.receiptbook.sequence_id.number_next_actual).zfill(8),
        )

        vals = {
            "journal_id": self.bank_journal.id,
            "amount": invoice.amount_total,
            "date": self.today,
        }
        action_context = invoice.action_register_payment()["context"]
        payment = self.env["account.payment"].with_context(**action_context).create(vals)
        payment.action_post()
        self.assertEqual(payment.name, expected_name, "no se tomo la secuencia correcta del pago")

    def test_payment_amount_update(self):
        """Test creating a payment, posting it, resetting to draft, updating amount, and validating name."""
        payment = self.env["account.payment"].create(
            {
                "amount": 100,
                "payment_type": "inbound",
                "partner_id": self.partner_ri.id,
                "journal_id": self.bank_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": self.receiptbook.id,
            }
        )

        # Post the payment
        payment.action_post()
        original_name = payment.name

        # Reset to draft
        payment.action_draft()

        # Update the amount
        payment.amount = 200

        # Post again
        payment.action_post()

        # Validate that the name remains the same
        self.assertEqual(
            payment.name,
            original_name,
            "The payment name should remain the same after updating the amount.",
        )

    def test_payment_name_uniqueness(self):
        """
        Create 2 payments with bank and cash journals, post them,
        try to resequence the first one with the name of the second and validate ValidationError.
        """
        cash_journal = self.env["account.journal"].search(
            [("company_id", "=", self.company.id), ("type", "=", "cash")], limit=1
        )
        if not cash_journal:
            cash_journal = self.env["account.journal"].create(
                {"type": "cash", "name": "Cash", "company_id": self.company.id}
            )
        # Pagos directos contra la cuenta del diario (sin outstanding) a propósito
        (cash_journal.outbound_payment_method_line_ids + cash_journal.inbound_payment_method_line_ids).write(
            {"payment_account_id": cash_journal.default_account_id.id}
        )
        (self.bank_journal.outbound_payment_method_line_ids + self.bank_journal.inbound_payment_method_line_ids).write(
            {"payment_account_id": self.bank_journal.default_account_id.id}
        )

        # Create first payment (bank)
        payment1 = self.env["account.payment"].create(
            {
                "amount": 100,
                "payment_type": "inbound",
                "partner_id": self.partner_ri.id,
                "journal_id": self.bank_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": self.receiptbook.id,
            }
        )
        payment1.action_post()
        payment1.filtered(lambda p: not p.move_id)._generate_journal_entry()

        # Create second payment (cash)
        payment2 = self.env["account.payment"].create(
            {
                "amount": 200,
                "payment_type": "inbound",
                "partner_id": self.partner_ri.id,
                "journal_id": cash_journal.id,
                "date": self.today,
                "company_id": self.company.id,
                "receiptbook_id": self.receiptbook.id,
            }
        )
        payment2.action_post()
        payment2.filtered(lambda p: not p.move_id)._generate_journal_entry()

        # Try to resequence the first payment with the name of the second
        resequence_wizard = self.env["account.resequence.wizard"].create(
            {
                "move_ids": [(6, 0, [payment1.move_id.id])],
                "ordering": "keep",
                "new_values": json.dumps(
                    {
                        str(payment1.move_id.id): {
                            "new_by_name": payment2.name,
                            "new_by_date": payment2.name,
                        }
                    }
                ),
                "first_name": payment2.name,
            }
        )
        with self.assertRaises(ValidationError) as cm:
            resequence_wizard.resequence()
        self.assertIn("already exist", str(cm.exception))

    def _create_branch(self):
        """Minimal branch under the test AR company (reuses its chart)."""
        return self.env["res.company"].create({"name": "Test Branch", "parent_id": self.company.id})

    def test_branch_prefix_constraint(self):
        """A branch cannot reuse a receiptbook prefix of its parent tree."""
        RB = self.env["account.payment.receiptbook"]
        branch = self._create_branch()
        doc_type = self.receiptbook.document_type_id
        # Same prefix/document_type/partner_type as the parent 0001- receiptbook -> blocked.
        with self.assertRaises(UserError):
            RB.create(
                {
                    "name": "Branch dup",
                    "partner_type": "customer",
                    "company_id": branch.id,
                    "document_type_id": doc_type.id,
                    "prefix": self.receiptbook.prefix,
                }
            )
        # A free prefix is accepted.
        rb = RB.create(
            {
                "name": "Branch ok",
                "partner_type": "customer",
                "company_id": branch.id,
                "document_type_id": doc_type.id,
                "prefix": "0099-",
            }
        )
        self.assertTrue(rb.id)

    def test_branch_default_prefix(self):
        """Auto-created branch receiptbooks pick the first free prefix in the tree."""
        branch = self._create_branch()
        self.env["account.chart.template"]._create_receiptbooks(branch)
        branch_rb = self.env["account.payment.receiptbook"].search(
            [("company_id", "=", branch.id), ("partner_type", "=", "customer")], limit=1
        )
        # Parent keeps 0001-, so the branch bumps to 0002-.
        self.assertEqual(branch_rb.prefix, "0002-")

    def test_branch_prefix_collision_migration(self):
        """_resolve_branch_prefix_collisions reassigns the branch and keeps the root."""
        RB = self.env["account.payment.receiptbook"]
        branch = self._create_branch()
        branch_rb = RB.create(
            {
                "name": "Branch cust",
                "partner_type": "customer",
                "company_id": branch.id,
                "document_type_id": self.receiptbook.document_type_id.id,
                "prefix": "0050-",
            }
        )
        # Force a legacy collision with the parent prefix, bypassing the constraint.
        self.env.cr.execute(
            "UPDATE account_payment_receiptbook SET prefix=%s WHERE id=%s",
            (self.receiptbook.prefix, branch_rb.id),
        )
        self.env.invalidate_all()
        self.assertEqual(branch_rb.prefix, self.receiptbook.prefix)

        reassigned = RB._resolve_branch_prefix_collisions()
        self.assertIn(branch_rb, reassigned)
        self.assertNotEqual(branch_rb.prefix, self.receiptbook.prefix)
        self.assertEqual(self.receiptbook.prefix, "0001-")
        self.assertEqual(branch_rb.sequence_id.prefix, branch_rb.prefix)
        # Idempotent: a second run reassigns nothing.
        self.assertFalse(RB._resolve_branch_prefix_collisions())
