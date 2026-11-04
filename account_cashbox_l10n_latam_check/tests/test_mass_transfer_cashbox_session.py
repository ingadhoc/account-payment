# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from unittest import mock

from odoo import Command, fields
from odoo.addons.l10n_latam_check.tests.common import L10nLatamCheckTest
from odoo.exceptions import UserError
from odoo.tests import Form, common, tagged

TRANSFER_MODEL = "l10n_latam.payment.mass.transfer"


@tagged("post_install", "-at_install")
class TestMassTransferCashboxSessionChoice(common.TransactionCase):
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
                "group_ids": [(6, 0, cls.env.ref("account.group_account_user").ids)],
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
        return self.env[TRANSFER_MODEL].with_user(user or self.cashier).create(values)

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
        wizard = self._wizard(to_journal_id=self.journal_a.id)
        self.assertFalse(wizard.cashbox_session_id, "With several candidates none is picked for the user")

        wizard.cashbox_session_id = chosen
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_chosen_session_given_on_create_survives_reload(self):
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(to_journal_id=self.journal_a.id, cashbox_session_id=chosen.id)

        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_create_payments_uses_the_chosen_session_after_reload(self):
        """The user needs the session on each transfer: after the reload the guard has to let it pass
        and the payments have to get the chosen session."""
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(to_journal_id=self.journal_a.id)
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
        wizard = self._wizard(to_journal_id=self.journal_a.id, cashbox_session_id=chosen.id)
        wizard = self._reload(wizard)

        self.assertTrue(wizard.cashbox_session_ids_domain)
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_domain_lists_the_sessions_of_the_destination_journal(self):
        first = self._open_session(self.journal_a, name="First")
        second = self._open_session(self.journal_a, name="Second")
        self._open_session(self.journal_b, name="Other journal")
        self._open_session(self.journal_a, user=self.other_cashier, name="Other user")
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        sessions = self.env["account.cashbox.session"].search(wizard.cashbox_session_ids_domain)

        self.assertEqual(sessions, first | second)

    def test_domain_follows_the_destination_journal(self):
        self._open_session(self.journal_a)
        session_b = self._open_session(self.journal_b)
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        wizard.to_journal_id = self.journal_b

        sessions = self.env["account.cashbox.session"].search(wizard.cashbox_session_ids_domain)
        self.assertEqual(sessions, session_b)

    # The automatic choice keeps working

    def test_single_session_is_picked_and_survives_reload(self):
        session = self._open_session(self.journal_a)
        wizard = self._wizard(to_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session)

        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, session)

    def test_no_session_for_the_journal_leaves_it_empty(self):
        self._open_session(self.journal_b)
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        wizard = self._reload(wizard)

        self.assertFalse(wizard.cashbox_session_id)

    def test_session_of_other_journals_are_not_candidates(self):
        """Two sessions open, but only one has the destination journal: that one is picked."""
        session_a = self._open_session(self.journal_a)
        self._open_session(self.journal_b)
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, session_a)

    def test_closed_session_is_not_a_candidate(self):
        closed = self._open_session(self.journal_a, name="Closed")
        closed.state = "closed"
        open_session = self._open_session(self.journal_a, name="Open")
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, open_session)

    def test_session_of_another_user_is_not_a_candidate(self):
        self._open_session(self.journal_a, user=self.other_cashier, name="Other")
        mine = self._open_session(self.journal_a, user=self.cashier, name="Mine")
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, mine)

    def test_session_without_users_is_a_candidate(self):
        free = self._open_session(self.journal_a, name="Free")
        self._open_session(self.journal_a, user=self.other_cashier, name="Other")
        wizard = self._wizard(to_journal_id=self.journal_a.id)

        self.assertEqual(wizard.cashbox_session_id, free)

    # Changing the destination journal

    def test_changing_the_journal_picks_the_session_of_the_new_one(self):
        session_a = self._open_session(self.journal_a)
        session_b = self._open_session(self.journal_b)
        wizard = self._wizard(to_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session_a)

        wizard.to_journal_id = self.journal_b
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, session_b)

    def test_changing_to_a_journal_with_several_sessions_clears_the_session(self):
        session_a = self._open_session(self.journal_a)
        self._open_session(self.journal_b, name="B1")
        self._open_session(self.journal_b, name="B2")
        wizard = self._wizard(to_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session_a)

        wizard.to_journal_id = self.journal_b
        wizard = self._reload(wizard)

        self.assertFalse(wizard.cashbox_session_id)

    def test_changing_to_a_journal_without_sessions_clears_the_session(self):
        session_a = self._open_session(self.journal_a)
        wizard = self._wizard(to_journal_id=self.journal_a.id)
        self.assertEqual(wizard.cashbox_session_id, session_a)

        wizard.to_journal_id = self.journal_c
        wizard = self._reload(wizard)

        self.assertFalse(wizard.cashbox_session_id)

    def test_choice_is_kept_when_the_journal_is_written_again_with_the_same_value(self):
        self._open_session(self.journal_a, name="First")
        chosen = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(to_journal_id=self.journal_a.id, cashbox_session_id=chosen.id)

        wizard.write({"to_journal_id": self.journal_a.id})
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, chosen)

    def test_choice_can_be_replaced(self):
        first = self._open_session(self.journal_a, name="First")
        second = self._open_session(self.journal_a, name="Second")
        wizard = self._wizard(to_journal_id=self.journal_a.id, cashbox_session_id=first.id)

        wizard.cashbox_session_id = second
        wizard = self._reload(wizard)

        self.assertEqual(wizard.cashbox_session_id, second)

    # The guard of _create_payments

    def test_user_that_requires_session_cannot_transfer_without_one(self):
        self._open_session(self.journal_a, name="First")
        self._open_session(self.journal_a, name="Second")
        wizard = self._reload(self._wizard(to_journal_id=self.journal_a.id))

        with self.assertRaises(UserError):
            wizard._create_payments()

    def test_user_that_does_not_require_session_can_transfer_without_one(self):
        self._open_session(self.journal_a, name="First")
        self._open_session(self.journal_a, name="Second")
        wizard = self._reload(self._wizard(user=self.free_user, to_journal_id=self.journal_a.id))
        self.assertFalse(wizard.cashbox_session_id)

        payments = self._patch_next_create_payments()
        wizard._create_payments()

        self.assertFalse(payments.cashbox_session_id)


@tagged("post_install_l10n", "post_install", "-at_install")
class TestMassTransferCashboxSession(L10nLatamCheckTest):
    """La transferencia de cheques de terceros toma la sesión de caja abierta del
    diario destino y la deja en el pago, y la exige si el usuario la requiere."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # in 20 the third party checks setup moved from the common class to TestThirdChecks
        cls.company_data_3 = cls.setup_other_company(
            name="company_3_data",
            country_id=cls.env.ref("base.ar").id,
            currency_id=cls.env.ref("base.ARS").id,
        )
        cls.third_party_check_journal = cls.env["account.journal"].search(
            [
                ("company_id", "=", cls.company_data_3["company"].id),
                ("inbound_payment_method_line_ids.code", "=", "new_third_party_checks"),
            ],
            limit=1,
        )
        cls.destination_journal = cls.company_data_3["default_journal_bank"]
        cls.cashbox = cls.env["account.cashbox"].create(
            {
                "name": "Caja cheques",
                "company_id": cls.destination_journal.company_id.id,
                "journal_ids": [Command.link(cls.destination_journal.id)],
                "allow_concurrent_sessions": True,
            }
        )
        cls.session = cls.env["account.cashbox.session"].create({"cashbox_id": cls.cashbox.id, "name": "S-1"})
        cls.session.action_account_cashbox_session_open()

    def _create_check(self):
        journal = self.third_party_check_journal
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "inbound",
                "journal_id": journal.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": "00000001",
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 1,
                        }
                    ),
                ],
                "payment_method_line_id": journal._get_available_payment_method_lines("inbound")
                .filtered(lambda x: x.code == "new_third_party_checks")
                .id,
            }
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _transfer_wizard(self, check):
        return (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=check.ids)
            .create({"to_journal_id": self.destination_journal.id})
        )

    def test_transfer_takes_destination_session(self):
        check = self._create_check()
        wizard = self._transfer_wizard(check)
        self.assertEqual(wizard.cashbox_session_id, self.session)
        payment = wizard._create_payments()
        self.assertEqual(payment.cashbox_session_id, self.session)

    def test_transfer_form_offers_destination_session(self):
        check = self._create_check()
        wizard_model = self.env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check", active_ids=check.ids
        )
        with Form(wizard_model) as form:
            form.to_journal_id = self.destination_journal
            self.assertIn(
                self.session.id, self.env["account.cashbox.session"].search(form.cashbox_session_ids_domain).ids
            )

    def test_transfer_requires_session(self):
        check = self._create_check()
        self.env.user.requiere_account_cashbox_session = True
        self.session.action_closing_control()
        wizard = self._transfer_wizard(check)
        self.assertFalse(wizard.cashbox_session_id)
        with self.assertRaisesRegex(UserError, "requires to use payment session"):
            wizard._create_payments()
