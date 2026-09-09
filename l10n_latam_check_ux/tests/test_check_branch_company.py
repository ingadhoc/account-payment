##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.tests.common import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestCheckBranchCompany(LatamCheckCommon):
    """Which company owns a check that travels between branches.

    A check moved to another branch and back must end up owned by the company
    it came from. When only the journal goes back, the check keeps a
    company/journal pair no payment domain can satisfy and disappears from both
    companies at once.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env["res.company"].create({"name": "Test Branch", "parent_id": cls.company.id})
        cls.branch.transfer_account_id = cls.company.transfer_account_id
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=(cls.company + cls.branch).ids))
        cls.partner.with_company(cls.branch).write(
            {
                "property_account_receivable_id": cls.receivable_account.id,
                "property_account_payable_id": cls.destination_account.id,
            }
        )
        cls.branch_journal = cls.env["account.journal"].create(
            {"name": "Branch Third Party Checks", "code": "BTPC", "type": "cash", "company_id": cls.branch.id}
        )
        for method, label in (
            (cls.new_third_party_method, "New Third Party Checks"),
            (cls.in_third_party_method, "Existing Third Party Checks"),
            (cls.out_third_party_method, "Deliver Third Party Checks"),
        ):
            cls._add_method_line(cls.branch_journal, method, label, cls.third_party_account)

    def _receive_in_branch(self, number):
        branch_line = self._get_method_line(self.branch_journal, "new_third_party_checks")
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.branch_journal.id,
                "company_id": self.branch.id,
                "date": self.today,
                "payment_method_line_id": branch_line.id,
                "l10n_latam_new_check_ids": [Command.create(self._new_check_vals(100.0, number, issuer=True))],
            }
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _transfer_to_parent(self, check):
        transfer = self.env["account.payment"].create(
            {
                "partner_id": self.branch.partner_id.id,
                "payment_type": "outbound",
                "is_internal_transfer": True,
                "journal_id": self.branch_journal.id,
                "destination_company_id": self.company.id,
                "destination_journal_id": self.third_party_journal.id,
                "payment_method_line_id": self._get_method_line(self.branch_journal, "out_third_party_checks").id,
                "l10n_latam_move_check_ids": [Command.set(check.ids)],
                "amount": 100.0,
            }
        )
        transfer.action_post()
        return transfer + transfer.paired_internal_transfer_payment_id

    def test_transfer_between_branches_moves_the_check_company(self):
        check = self._receive_in_branch("UX-BRANCH-0001")
        self.assertEqual(check.company_id, self.branch)
        self.assertEqual(check.current_journal_id, self.branch_journal)

        self._transfer_to_parent(check)

        self.assertEqual(check.current_journal_id, self.third_party_journal)
        self.assertEqual(check.company_id, self.company, "the receiving company must own the check")

    def test_cancelled_transfer_gives_the_check_back(self):
        check = self._receive_in_branch("UX-BRANCH-0002")
        operations = self._transfer_to_parent(check)
        self.assertEqual(check.company_id, self.company)

        operations.action_cancel()

        self.assertEqual(check.current_journal_id, self.branch_journal)
        self.assertEqual(check.company_id, self.branch, "a cancelled transfer must not keep the check")

    def test_deleted_transfer_gives_the_check_back(self):
        """Same as cancelling, walked to the end: the operations are deleted."""
        check = self._receive_in_branch("UX-BRANCH-0003")
        operations = self._transfer_to_parent(check)
        self.assertEqual(check.company_id, self.company)

        operations.action_cancel()
        operations.unlink()

        self.assertEqual(check.operation_ids, self.env["account.payment"])
        self.assertEqual(check.current_journal_id, self.branch_journal)
        self.assertEqual(check.company_id, self.branch, "a deleted transfer must not keep the check")
