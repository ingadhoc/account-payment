# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests import common, tagged

TRANSFER_MODEL = "l10n_latam.payment.mass.transfer"


@tagged("post_install", "-at_install")
class TestMassTransferCashboxSession(common.TransactionCase):
    """The cashbox session picked in the check transfer wizard has to survive the save of the wizard.

    The web client saves the wizard and then runs the button in another request, so whatever the user
    chose has to be stored: a value kept only in memory is computed again and, with several candidate
    sessions, ends up empty.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # only the sessions of this test compete for the wizard
        cls.env["account.cashbox.session"].search([("state", "=", "opened")]).write({"state": "closed"})
        cls.outstanding = cls.env["account.account"].create(
            {"name": "Cashbox test outstanding", "code": "CBT998", "account_type": "asset_current", "reconcile": True}
        )
        cls.journal_a = cls._create_journal("CBWA")
        cls.journal_b = cls._create_journal("CBWB")
        cls.journal_c = cls._create_journal("CBWC")
        cls.cashier = cls._create_user("cashbox_wizard_cashier", requires_session=True)
        cls.other_cashier = cls._create_user("cashbox_wizard_other", requires_session=True)
        cls.free_user = cls._create_user("cashbox_wizard_free", requires_session=False)

    def setUp(self):
        super().setUp()

        # the wizard computes its journal and company from the checks, which these tests do not need
        def _compute_journal_company(wizard):
            wizard.journal_id = self.journal_c
            wizard.company_id = self.company

        self.patch(type(self.env[TRANSFER_MODEL]), "_compute_journal_company", _compute_journal_company)

    @classmethod
    def _create_journal(cls, code):
        journal = cls.env["account.journal"].create(
            {"name": code, "code": code, "type": "cash", "company_id": cls.company.id}
        )
        (
            journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
        ).payment_account_id = cls.outstanding
        return journal

    @classmethod
    def _create_user(cls, login, requires_session):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "email": f"{login}@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, cls.company.ids)],
                "groups_id": [(6, 0, cls.env.ref("account.group_account_user").ids)],
                "requiere_account_cashbox_session": requires_session,
            }
        )

    def _open_session(self, journals, user=None, name=None):
        """Open a session on a new cashbox that has the given journals. Without user the session is free."""
        name = name or f"Cashbox {self.env['account.cashbox'].search_count([]) + 1}"
        sequence = self.env["ir.sequence"].create(
            {"name": name, "implementation": "no_gap", "company_id": self.company.id}
        )
        cashbox = self.env["account.cashbox"].create(
            {
                "name": name,
                "company_id": self.company.id,
                "journal_ids": [(6, 0, journals.ids)],
                "sequence_id": sequence.id,
            }
        )
        session = self.env["account.cashbox.session"].create({"cashbox_id": cashbox.id})
        session.action_account_cashbox_session_open()
        session.user_ids = user or self.env["res.users"]
        return session

    def _wizard(self, user=None, **values):
        # no checks are needed: the cashbox field does not depend on them
        return (
            self.env[TRANSFER_MODEL]
            .with_user(user or self.cashier)
            .with_context(active_model="l10n_latam.check", active_ids=[])
            .create(values)
        )

    def _patch_next_create_payments(self, payments=None):
        """Replace the _create_payments that comes after the one of this module, whichever module it is."""
        payments = payments if payments is not None else mock.MagicMock()
        mro = type(self.env[TRANSFER_MODEL]).__mro__
        own = next(
            i for i, cls in enumerate(mro) if cls.__module__.startswith("odoo.addons.account_cashbox_l10n_latam")
        )
        parent = next(cls for cls in mro[own + 1 :] if "_create_payments" in cls.__dict__)
        self.patch(parent, "_create_payments", mock.Mock(return_value=payments))
        return payments

    def _reload(self, wizard):
        """What happens between the save of the wizard and the click on the button: a new request."""
        wizard.env.flush_all()
        wizard.env.invalidate_all()
        return wizard.browse(wizard.id)

    # The reported case

    def test_chosen_session_survives_reload_with_several_sessions(self):
        """Dipromas: several open sessions with the same journal, the user picks one."""
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        self._open_session(self.journal_a, name="Third")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)
        self.assertFalse(wizard.cashbox_session_id, "With several candidates none is picked for the user")

        wizard.cashbox_session_id = chosen
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_chosen_session_given_on_create_survives_reload(self):
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(destination_journal_id=self.journal_a.id, cashbox_session_id=chosen.id)

        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_create_payments_uses_the_chosen_session_after_reload(self):
        """The user needs the session on each transfer: after the reload the guard has to let it pass
        and the payments have to get the chosen session."""
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)
        wizard.cashbox_session_id = chosen
        wizard = self._reload(wizard)

        payments = self._patch_next_create_payments()
        result = wizard._create_payments()

        self.assertIs(result, payments)
        self.assertEqual(payments.cashbox_session_id, chosen.id)

    def test_reading_the_domain_does_not_clear_the_choice(self):
        """The web client reads the domain of the field right after saving the wizard."""
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(destination_journal_id=self.journal_a.id, cashbox_session_id=chosen.id)
        wizard = self._reload(wizard)

        self.assertTrue(wizard.cashbox_session_ids_domain)
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_domain_lists_the_sessions_of_the_destination_journal(self):
        first = self._open_session(self.journal_a, name="First")
        second = self._open_session(self.journal_a, name="Second")
        self._open_session(self.journal_b, name="Other journal")
        self._open_session(self.journal_a, user=self.other_cashier, name="Other user")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        sessions = self.env["account.cashbox.session"].search(wizard.cashbox_session_ids_domain)

        self.assertEqual(sessions, first | second)

    def test_domain_follows_the_destination_journal(self):
        self._open_session(self.journal_a)
        session_b = self._open_session(self.journal_b)
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        wizard.destination_journal_id = self.journal_b

        sessions = self.env["account.cashbox.session"].search(wizard.cashbox_session_ids_domain)
        self.assertEqual(sessions, session_b)

    # The automatic choice keeps working

    def test_single_session_is_picked_and_survives_reload(self):
        session = self._open_session(self.journal_a)
        wizard = self._wizard(destination_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session)

        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, session)

    def test_no_session_for_the_journal_leaves_it_empty(self):
        self._open_session(self.journal_b)
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        wizard = self._reload(wizard)

        self.assertFalse(wizard.cashbox_session_id)

    def test_without_destination_journal_leaves_it_empty(self):
        self._open_session(self.journal_a)
        wizard = self._wizard()

        self.assertFalse(wizard.cashbox_session_id)

    def test_session_of_other_journals_are_not_candidates(self):
        """Two sessions open, but only one has the destination journal: that one is picked."""
        session_a = self._open_session(self.journal_a)
        self._open_session(self.journal_b)
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, session_a)

    def test_closed_session_is_not_a_candidate(self):
        closed = self._open_session(self.journal_a, name="Closed")
        closed.state = "closed"
        open_session = self._open_session(self.journal_a, name="Open")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, open_session)

    def test_session_of_another_user_is_not_a_candidate(self):
        self._open_session(self.journal_a, user=self.other_cashier, name="Other")
        mine = self._open_session(self.journal_a, user=self.cashier, name="Mine")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, mine)

    def test_session_without_users_is_a_candidate(self):
        free = self._open_session(self.journal_a, name="Free")
        self._open_session(self.journal_a, user=self.other_cashier, name="Other")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, free)

    # Changing the destination journal

    def test_changing_the_journal_picks_the_session_of_the_new_one(self):
        session_a = self._open_session(self.journal_a)
        session_b = self._open_session(self.journal_b)
        wizard = self._wizard(destination_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session_a)

        wizard.destination_journal_id = self.journal_b
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, session_b)

    def test_changing_to_a_journal_with_several_sessions_clears_the_session(self):
        session_a = self._open_session(self.journal_a)
        self._open_session(self.journal_b, name="B1")
        self._open_session(self.journal_b, name="B2")
        wizard = self._wizard(destination_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session_a)

        wizard.destination_journal_id = self.journal_b
        wizard = self._reload(wizard)

        self.assertFalse(wizard.cashbox_session_id)

    def test_changing_to_a_journal_without_sessions_clears_the_session(self):
        session_a = self._open_session(self.journal_a)
        wizard = self._wizard(destination_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session_a)

        wizard.destination_journal_id = self.journal_c
        wizard = self._reload(wizard)

        self.assertFalse(wizard.cashbox_session_id)

    def test_choice_is_kept_when_the_journal_is_written_again_with_the_same_value(self):
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(destination_journal_id=self.journal_a.id, cashbox_session_id=chosen.id)

        wizard.write({"destination_journal_id": self.journal_a.id})
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_choice_can_be_replaced(self):
        first = self._open_session(self.journal_a, name="First")
        second = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(destination_journal_id=self.journal_a.id, cashbox_session_id=first.id)

        wizard.cashbox_session_id = second
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, second)

    # The guard of _create_payments

    def test_user_that_requires_session_cannot_transfer_without_one(self):
        self._open_session(self.journal_a, name="First")
        self._open_session(self.journal_a, name="Second")
        wizard = self._reload(self._wizard(destination_journal_id=self.journal_a.id))

        with self.assertRaises(UserError):
            wizard._create_payments()

    def test_user_that_does_not_require_session_can_transfer_without_one(self):
        self._open_session(self.journal_a, name="First")
        self._open_session(self.journal_a, name="Second")
        wizard = self._reload(self._wizard(user=self.free_user, destination_journal_id=self.journal_a.id))
        self.assertFalse(wizard.cashbox_session_id)

        payments = self._patch_next_create_payments()
        wizard._create_payments()

        self.assertFalse(payments.cashbox_session_id)
