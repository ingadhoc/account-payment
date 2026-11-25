##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Check state, the list actions offered by state and the checks dashboard (task 80427)."""

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestCheckStateActions(LatamCheckCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rejected_journal.l10n_latam_rejected_checks = True

    def _receive(self, amounts, numbers):
        receipt = self._receive_third_party_checks(amounts, numbers=numbers)
        receipt.action_post()
        return receipt.l10n_latam_new_check_ids

    def _wizard_from_action(self, action, vals):
        """Create the wizard the way the web client does: with the context of the action."""
        return self.env[action["res_model"]].with_context(**action["context"]).create(vals)

    def _deposit(self, checks):
        action = checks.action_check_deposit()
        self._wizard_from_action(action, {"to_journal_id": self.bank_journal.id})._create_payments()
        checks.invalidate_recordset()

    def _endorse(self, checks):
        endorsement = self._deliver_third_party_checks(checks)
        endorsement.action_post()
        checks.invalidate_recordset()
        return endorsement

    def _reject(self, checks):
        action = checks.action_check_reject()
        wizard = self._wizard_from_action(action, {"date": self.today})
        self.assertEqual(
            wizard.rejected_journal_id, self.rejected_journal, "The journal flagged as rejected is proposed"
        )
        wizard.action_confirm()
        checks.invalidate_recordset()

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    def test_third_party_check_state_follows_its_operations(self):
        deposited, endorsed = self._receive([100.0, 200.0], ["00080001", "00080002"])

        with self.subTest("a received check is in portfolio"):
            self.assertEqual(deposited.check_state, "on_hand")
            self.assertEqual(endorsed.check_state, "on_hand")

        with self.subTest("deposited on a bank journal"):
            self._deposit(deposited)
            self.assertEqual(deposited.check_state, "deposited")

        with self.subTest("endorsed to a vendor"):
            self._endorse(endorsed)
            self.assertEqual(endorsed.check_state, "endorsed")

        with self.subTest("rejected checks are returned to the customer by the wizard"):
            self._reject(endorsed)
            self.assertEqual(endorsed.check_state, "returned")

    def test_check_in_the_rejected_journal_is_rejected(self):
        """The rejected checks journal is of type cash: the flag goes before "in portfolio"."""
        check = self._receive([100.0], ["00080011"])
        action = check.action_check_transfer()
        self._wizard_from_action(action, {"to_journal_id": self.rejected_journal.id})._create_payments()
        check.invalidate_recordset()
        self.assertEqual(check.current_journal_id, self.rejected_journal)
        self.assertEqual(check.check_state, "rejected")

        self.rejected_journal.l10n_latam_rejected_checks = False
        self.assertEqual(check.check_state, "on_hand", "Unflagging the journal recomputes the state")

    def test_own_check_state_copies_issue_state(self):
        payment = self._create_own_check_payment([100.0], numbers=["00080021"])
        payment.action_post()
        check = payment.l10n_latam_new_check_ids
        self.assertEqual(check.issue_state, "handed")
        self.assertEqual(check.check_state, "handed")

    # ------------------------------------------------------------------
    # actions offered by state
    # ------------------------------------------------------------------
    def test_checks_in_portfolio_of_one_journal_accept_every_portfolio_action(self):
        checks = self._receive([100.0, 200.0, 300.0], ["00080031", "00080032", "00080033"])
        for action in ("deposit", "transfer", "endorse", "return"):
            with self.subTest(action=action):
                self.assertEqual(checks._get_check_action_errors(action), [])

    def test_action_that_does_not_apply_names_the_check_and_opens_nothing(self):
        on_hand, deposited = self._receive([100.0, 200.0], ["00080041", "00080042"])
        self._deposit(deposited)
        with self.assertRaisesRegex(UserError, "00080042") as error:
            (on_hand + deposited).action_check_deposit()
        self.assertNotIn("00080041", str(error.exception), "Only the check that does not admit it is listed")

    def test_portfolio_actions_move_checks_of_one_journal(self):
        portfolio_b = self._create_third_party_journal("Test Third Party Checks B", "TTPCB")
        check_a, check_b = self._receive([100.0, 200.0], ["00080051", "00080052"])
        self._wizard_from_action(check_b.action_check_transfer(), {"to_journal_id": portfolio_b.id})._create_payments()
        (check_a + check_b).invalidate_recordset()
        for action in ("action_check_deposit", "action_check_transfer"):
            with self.subTest(action=action), self.assertRaisesRegex(UserError, "different journals"):
                getattr(check_a + check_b, action)()

    def test_reject_only_applies_to_deposited_or_endorsed_checks(self):
        check = self._receive([100.0], ["00080061"])
        with self.assertRaises(UserError):
            check.action_check_reject()
        self._endorse(check)
        self.assertEqual(check.action_check_reject()["res_model"], "account.check.reject.wizard")

    def test_own_check_actions(self):
        payment = self._create_own_check_payment([100.0, 200.0], numbers=["00080071", "00080072"])
        payment.action_post()
        checks = payment.l10n_latam_new_check_ids
        self.assertEqual(checks.action_check_debit()["res_model"], "account.check.action.wizard")
        with self.assertRaisesRegex(UserError, "one at a time"):
            checks.action_check_void()
        with self.assertRaises(UserError, msg="Third party actions do not apply to own checks"):
            checks.action_check_deposit()

    # ------------------------------------------------------------------
    # deposit and transfer narrow the destination
    # ------------------------------------------------------------------
    def test_deposit_goes_to_a_bank_and_transfer_does_not(self):
        portfolio_b = self._create_third_party_journal("Test Third Party Checks B", "TTPCB")
        check = self._receive([100.0], ["00080081"])
        with self.assertRaises(ValidationError):
            self._wizard_from_action(check.action_check_deposit(), {"to_journal_id": portfolio_b.id})
        with self.assertRaises(ValidationError):
            self._wizard_from_action(check.action_check_transfer(), {"to_journal_id": self.bank_journal.id})

    # ------------------------------------------------------------------
    # endorse and return open a draft payment with the checks loaded
    # ------------------------------------------------------------------
    def test_endorse_and_return_prefill_the_payment(self):
        checks = self._receive([100.0, 200.0], ["00080091", "00080092"])
        for action, partner_type, code in (
            ("action_check_endorse", "supplier", "out_third_party_checks"),
            ("action_check_return", "customer", "out_third_party_checks"),
        ):
            with self.subTest(action=action):
                context = getattr(checks, action)()["context"]
                self.assertEqual(context["default_partner_type"], partner_type)
                self.assertEqual(context["default_journal_id"], self.third_party_journal.id)
                payment = self.env["account.payment"].with_context(**context).create({"partner_id": self.partner.id})
                self.assertEqual(payment.state, "draft")
                self.assertEqual(payment.payment_method_line_id.code, code)
                self.assertEqual(payment.l10n_latam_move_check_ids, checks)
                self.assertEqual(payment.amount, 300.0)

    # ------------------------------------------------------------------
    # dashboard
    # ------------------------------------------------------------------
    def test_dashboard_cards_add_up_to_the_third_party_checks(self):
        on_hand, deposited, endorsed = self._receive([100.0, 200.0, 300.0], ["00080101", "00080102", "00080103"])
        self._deposit(deposited)
        self._endorse(endorsed)

        sections = {section["key"]: section for section in self.env["l10n_latam.check"].get_check_dashboard_data()}
        cards = {card["key"]: card for card in sections["third_party"]["cards"]}
        third_party_checks = self.env["l10n_latam.check"].search(
            [("payment_method_line_id.code", "=", "new_third_party_checks"), ("company_id", "=", self.company.id)]
        )
        state_cards = [card for key, card in cards.items() if key != "due_week"]
        self.assertEqual(sum(card["count"] for card in state_cards), len(third_party_checks))
        self.assertEqual(
            sum(amount["amount"] for card in state_cards for amount in card["amounts"]),
            sum(third_party_checks.mapped("amount")),
        )
        self.assertGreaterEqual(cards["on_hand"]["count"], 1)
        self.assertGreaterEqual(cards["due_week"]["count"], 1, "The checks are payable today")

    def test_dashboard_card_opens_the_list_filtered_by_its_state(self):
        action = self.env["l10n_latam.check"].action_open_dashboard_card("third_party", "deposited")
        self.assertEqual(action["context"], {"search_default_check_state_deposited": 1})
        action = self.env["l10n_latam.check"].action_open_dashboard_card("own", "due_week")
        self.assertEqual(action["context"], {"search_default_checks_handed": 1, "search_default_due_week": 1})
