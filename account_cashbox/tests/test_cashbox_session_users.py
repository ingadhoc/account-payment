from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestCashboxSessionUsers(common.TransactionCase):
    """En una caja que restringe usuarios, la sesión solo puede tener usuarios
    permitidos en la caja. Los managers contables quedan afuera del control."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "cash"), ("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.allowed_user = cls._create_user("cashbox_allowed_test", "account.group_account_invoice")
        cls.other_user = cls._create_user("cashbox_not_allowed_test", "account.group_account_invoice")
        cls.manager = cls._create_user("cashbox_manager_test", "account.group_account_manager")
        cls.cashbox = cls.env["account.cashbox"].create(
            {
                "name": "Caja restringida",
                "company_id": cls.env.company.id,
                "journal_ids": [Command.link(cls.journal.id)],
                "allow_concurrent_sessions": True,
                "restrict_users": True,
                "allowed_res_users_ids": [Command.set(cls.allowed_user.ids)],
            }
        )

    @classmethod
    def _create_user(cls, login, group):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "company_ids": [Command.set(cls.env.company.ids)],
                "company_id": cls.env.company.id,
                "group_ids": [Command.link(cls.env.ref(group).id)],
            }
        )

    def _create_session(self, users):
        return self.env["account.cashbox.session"].create(
            {"cashbox_id": self.cashbox.id, "name": "S-%s" % users[:1].login, "user_ids": [Command.set(users.ids)]}
        )

    def test_session_users_must_be_allowed(self):
        with self.assertRaisesRegex(ValidationError, "must be allowed on the cashbox"):
            self._create_session(self.allowed_user | self.other_user)

        session = self._create_session(self.allowed_user)
        with self.assertRaisesRegex(ValidationError, "must be allowed on the cashbox"):
            session.user_ids = [Command.link(self.other_user.id)]

    def test_manager_does_not_need_to_be_allowed(self):
        session = self._create_session(self.manager)
        self.assertEqual(session.user_ids, self.manager)
