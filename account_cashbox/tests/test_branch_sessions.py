##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.tests import tagged

from .common import CashboxCommon


@tagged("post_install", "-at_install")
class TestBranchSessions(CashboxCommon):
    """Sesiones disponibles cuando el usuario está parado en una sucursal.

    Es la lógica que decide a qué caja se imputa un cobro en un cliente con
    sucursales. No rompe ruidosamente cuando está mal: imputa a la caja
    equivocada, que es de las cosas más caras de depurar en producción.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env["res.company"].create({"name": "Test Cashbox Branch", "parent_id": cls.company.id})
        cls.sibling = cls.env["res.company"].create({"name": "Test Cashbox Sibling", "parent_id": cls.company.id})
        cls.cashbox_user.write({"company_ids": [Command.set((cls.company | cls.branch | cls.sibling).ids)]})
        cls.journal_branch = cls.env["account.journal"].create(
            {"name": "Test Branch Cash", "code": "TBRC", "type": "cash", "company_id": cls.branch.id}
        )
        cls.journal_sibling = cls.env["account.journal"].create(
            {"name": "Test Sibling Cash", "code": "TSIC", "type": "cash", "company_id": cls.sibling.id}
        )

    def _cashbox_en(self, company, name, journal):
        """Caja de otra compañía del árbol: se crea con with_company para que los
        chequeos de compañía del ORM la evalúen desde ahí."""
        return (
            self.env["account.cashbox"]
            .with_company(company)
            .create(
                {
                    "name": name,
                    "company_id": company.id,
                    "journal_ids": [Command.set(journal.ids)],
                    "restrict_users": True,
                    "allowed_res_users_ids": [Command.set(self.cashbox_user.ids)],
                    "allow_concurrent_sessions": True,
                }
            )
        )

    def test_desde_una_sucursal_solo_se_ven_las_sesiones_del_arbol(self):
        """Dado un usuario parado en una sucursal, cuando se listan las sesiones
        disponibles, entonces ve las de su sucursal y las de la empresa padre,
        y no ve las de una sucursal hermana.

        Cubre el comportamiento 23 del relevamiento oba-test de account_cashbox.
        """
        caja_padre = self._cashbox_en(self.company, "Caja del padre", self.journal_cash)
        caja_sucursal = self._cashbox_en(self.branch, "Caja de la sucursal", self.journal_branch)
        caja_hermana = self._cashbox_en(self.sibling, "Caja de la hermana", self.journal_sibling)

        todas = self.company | self.branch | self.sibling
        sesion_padre = self._create_session(caja_padre, name="Sesion padre", open_it=True, allowed_companies=todas)
        sesion_sucursal = self._create_session(
            caja_sucursal, name="Sesion sucursal", open_it=True, allowed_companies=todas
        )
        sesion_hermana = self._create_session(
            caja_hermana, name="Sesion hermana", open_it=True, allowed_companies=todas
        )

        Session = self.env["account.cashbox.session"].with_user(self.cashbox_user).with_company(self.branch)
        disponibles = Session.search(Session._get_available_domain(self.branch))
        creadas_por_el_test = sesion_padre | sesion_sucursal | sesion_hermana

        self.assertEqual(
            disponibles & creadas_por_el_test,
            sesion_padre | sesion_sucursal,
            "Desde la sucursal las sesiones disponibles son %s" % (disponibles & creadas_por_el_test).mapped("name"),
        )
        self.assertNotIn(
            sesion_hermana,
            disponibles,
            "Desde la sucursal se ofrece la sesión de una sucursal hermana: un cobro puede terminar imputado "
            "a la caja de otra sucursal",
        )

    def test_el_pago_de_una_sucursal_cae_en_una_compania_del_arbol_del_diario(self):
        """Dado una sucursal que cobra con un diario de la empresa padre, cuando se
        crea el pago, entonces la compañía del pago pertenece al árbol del
        diario.

        Cubre el comportamiento 32 del relevamiento oba-test de account_cashbox.
        """
        caja_padre = self._cashbox_en(self.company, "Caja compartida", self.journal_cash)
        sesion = self._create_session(
            caja_padre,
            name="Sesion compartida",
            open_it=True,
            allowed_companies=self.company | self.branch,
        )

        pago = (
            self.env["account.payment"]
            .with_user(self.cashbox_user)
            .with_company(self.branch)
            .create(
                {
                    "journal_id": self.journal_cash.id,
                    "amount": 90.0,
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner.id,
                    "cashbox_session_id": sesion.id,
                }
            )
        )
        # el pago se cobra con un diario del padre desde la sucursal: tiene que quedar colgado
        # de una compañía del árbol de ese diario, no de una rama ajena
        self.assertIn(
            self.journal_cash.sudo().company_id,
            pago.sudo().company_id.parent_ids,
            "El pago quedó en la compañía %s, que no desciende de la del diario" % pago.sudo().company_id.name,
        )
