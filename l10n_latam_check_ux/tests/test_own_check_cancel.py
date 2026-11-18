##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestOwnCheckCancel(LatamCheckCommon):
    def test_canceling_the_entry_releases_its_checks(self):
        payment = self._create_own_check_payment([100], numbers=["00009201"])
        payment.action_post()

        payment.move_id.button_draft()
        payment.move_id.button_cancel()

        self.assertFalse(payment.l10n_latam_new_check_ids.outstanding_line_id)
        self.assertFalse(payment.l10n_latam_new_check_ids.issue_state)
        reuse = self._create_own_check_payment([100], numbers=["00009201"])
        reuse.action_post()
        self.assertEqual(reuse.l10n_latam_new_check_ids.issue_state, "handed")

    def test_a_canceled_payment_posted_again_links_its_checks(self):
        payment = self._create_own_check_payment(
            [20, 30], numbers=["00009301", "00009302"], currency=self.foreign_currency
        )
        payment.action_post()
        payment.action_cancel()
        self.assertFalse(payment.l10n_latam_new_check_ids.outstanding_line_id)

        payment.action_draft()
        payment.action_post()

        self.assertEqual(payment.l10n_latam_new_check_ids.mapped("issue_state"), ["handed", "handed"])
        self.assert_move_balanced(payment.move_id)
        self.assert_check_lines_match(payment)
