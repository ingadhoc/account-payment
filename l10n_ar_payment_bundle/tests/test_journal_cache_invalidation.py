# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestJournalCacheInvalidation(TransactionCase):
    """A write touching the journal payment method lines must only invalidate the
    registry cache when the lines actually change.

    A no-op write (same line ids, e.g. the recompute of the stored computed
    ``inbound/outbound_payment_method_line_ids`` while loading the payments view)
    used to invalidate the whole registry on every write, signaling all workers to
    rebuild it. Under repeated reloads that produced an invalidation storm.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Test Bank",
                "type": "bank",
                "code": "TBNK1",
                "company_id": cls.company.id,
            }
        )

    def _write_method_lines(self, commands):
        with patch.object(type(self.env.registry), "clear_cache") as mock_clear:
            self.journal.write({"outbound_payment_method_line_ids": commands})
        return mock_clear.call_count

    def test_no_op_write_does_not_invalidate_cache(self):
        """Re-writing the same payment method line ids must NOT clear the cache."""
        current_ids = self.journal.outbound_payment_method_line_ids.ids
        calls = self._write_method_lines([Command.set(current_ids)])
        self.assertEqual(
            calls,
            0,
            "A no-op write of the payment method lines must not invalidate the registry cache.",
        )

    def test_real_change_invalidates_cache(self):
        """Actually removing a line must still clear the cache."""
        line = self.journal.outbound_payment_method_line_ids[:1]
        self.assertTrue(line, "The journal should have at least one outbound payment method line.")
        calls = self._write_method_lines([Command.unlink(line.id)])
        self.assertGreaterEqual(
            calls,
            1,
            "A real change of the payment method lines must invalidate the registry cache.",
        )
