##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import UserError
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestCashboxSessionAssignment(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # only the sessions of this test compete for the payment
        cls.env["account.cashbox.session"].search([("state", "=", "opened")]).write({"state": "closed"})
        cls.outstanding = cls.env["account.account"].create(
            {"name": "Cashbox test outstanding", "code": "CBT999", "account_type": "asset_current", "reconcile": True}
        )
        cls.journal_a = cls._create_journal("CBTA")
        cls.journal_b = cls._create_journal("CBTB")
        cls.journal_c = cls._create_journal("CBTC")
        cls.cashier = cls._create_user("cashbox_test_cashier")
        cls.other_cashier = cls._create_user("cashbox_test_other")
        cls.cashbox_a = cls._create_cashbox("Cashbox A", cls.journal_a)
        cls.cashbox_b = cls._create_cashbox("Cashbox B", cls.journal_b)
        cls.cashbox_c = cls._create_cashbox("Cashbox C", cls.journal_c)

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
    def _create_user(cls, login):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "email": f"{login}@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, cls.company.ids)],
                "groups_id": [(6, 0, cls.env.ref("account.group_account_user").ids)],
                "requiere_account_cashbox_session": True,
            }
        )

    @classmethod
    def _create_cashbox(cls, name, journal):
        sequence = cls.env["ir.sequence"].create(
            {"name": name, "implementation": "no_gap", "company_id": cls.company.id}
        )
        return cls.env["account.cashbox"].create(
            {
                "name": name,
                "company_id": cls.company.id,
                "journal_ids": [(6, 0, journal.ids)],
                "restrict_users": True,
                "sequence_id": sequence.id,
            }
        )

    def _open_session(self, cashbox, user):
        session = self.env["account.cashbox.session"].create({"cashbox_id": cashbox.id})
        session.action_account_cashbox_session_open()
        session.user_ids = user
        return session

    def _post_payment(self, journal, **values):
        payment = (
            self.env["account.payment"]
            .with_user(self.cashier)
            .create(dict({"payment_type": "inbound", "amount": 100.0, "journal_id": journal.id}, **values))
        )
        payment.action_post()
        return payment

    def test_several_sessions_take_the_one_of_the_journal(self):
        """With several open sessions, the payment goes to the one whose cashbox has its journal,
        not to the session of the default cashbox"""
        session_a = self._open_session(self.cashbox_a, self.cashier)
        self._open_session(self.cashbox_b, self.cashier)
        self.cashier.default_cashbox_id = self.cashbox_b
        payment = self._post_payment(self.journal_a)
        self.assertEqual(payment.cashbox_session_id, session_a)

    def test_default_session_must_take_the_journal(self):
        """The default cashbox session is not used when its cashbox does not have the journal"""
        self._open_session(self.cashbox_b, self.cashier)
        self._open_session(self.cashbox_c, self.cashier)
        self.cashier.default_cashbox_id = self.cashbox_b
        with self.assertRaises(UserError):
            self._post_payment(self.journal_a)

    def test_transfer_to_other_cashier_leaves_destination_free(self):
        """The destination payment of a transfer does not take a session by itself, so the cashier
        of the destination cashbox can import it into their own session"""
        session_a = self._open_session(self.cashbox_a, self.cashier)
        self._open_session(self.cashbox_b, self.other_cashier)
        transfer = self._post_payment(
            self.journal_a,
            payment_type="outbound",
            is_internal_transfer=True,
            destination_journal_id=self.journal_b.id,
            cashbox_session_id=session_a.id,
        )
        self.assertEqual(transfer.cashbox_session_id, session_a)
        self.assertFalse(transfer.paired_internal_transfer_payment_id.cashbox_session_id)
