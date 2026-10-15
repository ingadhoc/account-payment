from odoo import Command
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestCashboxVisibility(common.TransactionCase):
    """La visibilidad de la caja depende de restrict_users: sin restricción la ven
    todos los usuarios de facturación, aunque tenga usuarios cargados."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        journal = cls._create_cash_journal("CBXVI")
        cls.allowed_user = cls._create_user("cashbox_visibility_allowed")
        cls.other_user = cls._create_user("cashbox_visibility_other")
        cashbox_vals = {
            "company_id": cls.env.company.id,
            "journal_ids": [Command.link(journal.id)],
        }
        cls.restricted = cls.env["account.cashbox"].create(dict(cashbox_vals, name="Restringida", restrict_users=True))
        cls.restricted.allowed_res_users_ids = [Command.set(cls.allowed_user.ids)]
        cls.unrestricted = cls.env["account.cashbox"].create(dict(cashbox_vals, name="Sin restricción"))
        # same table as res.users.allowed_cashbox_ids: users loaded before 20 on an unrestricted cashbox
        cls.env.cr.execute(
            "INSERT INTO account_cashbox_users_rel (cashbox_id, user_id) VALUES (%s, %s)",
            (cls.unrestricted.id, cls.allowed_user.id),
        )
        cls.env.invalidate_all()

    @classmethod
    def _create_cash_journal(cls, code):
        # own suspense account: account_ux rejects a journal sharing it with the payment method
        suspense = cls.env["account.account"].create(
            {"name": "%s Suspense" % code, "code": "%sSUS" % code, "account_type": "asset_current"}
        )
        return cls.env["account.journal"].create(
            {"name": code, "code": code, "type": "cash", "suspense_account_id": suspense.id}
        )

    @classmethod
    def _create_user(cls, login):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "company_ids": [Command.set(cls.env.company.ids)],
                "company_id": cls.env.company.id,
                "group_ids": [Command.link(cls.env.ref("account.group_account_invoice").id)],
            }
        )

    def _visible(self, user):
        cashboxes = self.restricted | self.unrestricted
        return self.env["account.cashbox"].with_user(user).search([("id", "in", cashboxes.ids)])

    def test_visibility_depends_on_restrict_users(self):
        self.assertEqual(self._visible(self.allowed_user), self.restricted | self.unrestricted)
        self.assertEqual(self._visible(self.other_user), self.unrestricted)
