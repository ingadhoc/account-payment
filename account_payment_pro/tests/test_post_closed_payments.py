# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPostClosedPayments(AccountTestInvoicingCommon):
    """The list view "Post Payments" action calls action_post on every selected payment.

    The core sets the ones with a cash outstanding account to paid without looking at their
    state, so a canceled receipt came back as paid, with a new number and a posted entry.
    """

    def _create_payment(self, journal):
        return self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "inbound",
                "amount": 100.0,
                "journal_id": journal.id,
            }
        )

    def test_canceled_payment_is_skipped(self):
        payment = self._create_payment(self.company_data["default_journal_cash"])
        payment.action_cancel()

        payment.action_post()

        self.assertEqual(payment.state, "canceled")
        self.assertFalse(payment.move_id)

    def test_canceled_after_posting_is_skipped(self):
        payment = self._create_payment(self.company_data["default_journal_bank"])
        payment.action_post()
        payment.action_draft()
        payment.action_cancel()

        payment.action_post()

        self.assertEqual(payment.state, "canceled")

    def test_mixed_selection_skips_canceled(self):
        draft = self._create_payment(self.company_data["default_journal_bank"])
        canceled = self._create_payment(self.company_data["default_journal_cash"])
        canceled.action_cancel()

        (draft | canceled).action_post()

        self.assertEqual(draft.state, "in_process")
        self.assertEqual(canceled.state, "canceled")
        self.assertFalse(canceled.move_id)

    def test_canceled_payment_can_be_posted_after_reset_to_draft(self):
        payment = self._create_payment(self.company_data["default_journal_bank"])
        payment.action_cancel()
        payment.action_draft()

        payment.action_post()

        self.assertEqual(payment.state, "in_process")
