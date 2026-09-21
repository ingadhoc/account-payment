##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestCashboxSessionAutoAssign(common.TransactionCase):
    """A quien se le auto asigna una sesion de caja abierta en un pago nuevo"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.journal = cls.env["account.journal"].search([("type", "in", ["bank", "cash"])], limit=1)
        if not cls.journal:
            raise ValueError("No bank or cash journal found, can't run cashbox session tests.")
        cls.company = cls.journal.company_id

        cls.partner = cls.env["res.partner"].create({"name": "Test cashbox partner"})

        # una caja sin restriccion de usuarios: cualquiera puede operarla, que es el caso que
        # destapa el bug (la sesion no filtra por usuario en el dominio del compute)
        cls.cashbox = cls.env["account.cashbox"].create(
            {
                "name": "Test cashbox",
                "company_id": cls.company.id,
                "journal_ids": [(6, 0, cls.journal.ids)],
                "restrict_users": False,
                "sequence_id": cls.env["ir.sequence"]
                .create(
                    {
                        "name": "Test cashbox sessions",
                        "implementation": "no_gap",
                        "company_id": cls.company.id,
                    }
                )
                .id,
            }
        )
        cls.session = cls.env["account.cashbox.session"].create({"cashbox_id": cls.cashbox.id})
        cls.session.action_account_cashbox_session_open()

    @classmethod
    def _create_user(cls, login, **values):
        return cls.env["res.users"].create(
            dict(
                {
                    "name": login,
                    "login": login,
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, cls.company.ids)],
                    "groups_id": [(6, 0, cls.env.ref("account.group_account_user").ids)],
                },
                **values,
            )
        )

    def _create_payment(self, user):
        return (
            self.env["account.payment"]
            .with_user(user)
            .create(
                {
                    "payment_type": "inbound",
                    "partner_id": self.partner.id,
                    "amount": 100.0,
                    "journal_id": self.journal.id,
                }
            )
        )

    def test_no_session_for_foreign_cashbox(self):
        """Usuario que no opera con cajas: no hereda la sesion que abrio otro"""
        user = self._create_user("test_cashbox_outsider", requiere_account_cashbox_session=False)
        payment = self._create_payment(user)
        self.assertFalse(
            payment.cashbox_session_id,
            "Un usuario sin sesiones y sin esta caja no deberia recibir la sesion de otro",
        )

    def test_session_for_own_cashbox(self):
        """La caja es del usuario: se le asigna aunque no este obligado a usar sesiones"""
        user = self._create_user(
            "test_cashbox_owner",
            requiere_account_cashbox_session=False,
            allowed_cashbox_ids=[(6, 0, self.cashbox.ids)],
        )
        payment = self._create_payment(user)
        self.assertEqual(payment.cashbox_session_id, self.session)

    def test_session_for_required_user(self):
        """Usuario obligado a usar sesiones: se le asigna la unica abierta"""
        user = self._create_user("test_cashbox_required", requiere_account_cashbox_session=True)
        payment = self._create_payment(user)
        self.assertEqual(payment.cashbox_session_id, self.session)
