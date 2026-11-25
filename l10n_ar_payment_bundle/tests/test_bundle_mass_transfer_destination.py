# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleMassTransferDestination(TransactionCase):
    """Diario destino de la transferencia masiva de cheques con sucursales.

    El desplegable ofrece los diarios de todo el árbol de compañías: el cruce entre
    sucursales lo frena el wizard al confirmar, para que el usuario sepa que tiene que
    usar la transferencia interna. Los diarios bundle no se ofrecen en ninguna compañía.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].search(
            [("l10n_ar_tax_base_account_id", "!=", False), ("partner_id.country_id.code", "=", "AR")], limit=1
        )
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.env.user.company_id = cls.company
        cls.company.use_payment_pro = True

        cls.region = cls.env["res.company"].create({"name": "Test Bundle Región", "parent_id": cls.company.id})
        cls.branch = cls.env["res.company"].create({"name": "Test Bundle Sucursal", "parent_id": cls.region.id})
        cls.env.user.company_ids |= cls.region | cls.branch

        Journal = cls.env["account.journal"]
        cls.root_bank = Journal.create(
            {"name": "Test Bundle Banco CC", "type": "bank", "code": "TBMB1", "company_id": cls.company.id}
        )
        cls.branch_cash = Journal.create(
            {"name": "Test Bundle Caja Sucursal", "type": "cash", "code": "TBMC2", "company_id": cls.branch.id}
        )
        cls.branch_bank = Journal.create(
            {"name": "Test Bundle Banco Sucursal", "type": "bank", "code": "TBMB2", "company_id": cls.branch.id}
        )
        bundle_ids = {cls.company._get_bundle_journal("inbound"), cls.company._get_bundle_journal("outbound")}
        cls.bundle_journals = Journal.browse([journal_id for journal_id in bundle_ids if journal_id])

    def test_destination_offers_whole_tree_without_bundle_journals(self):
        wizard = self.env["l10n_latam.payment.mass.transfer"].new(
            {"company_id": self.branch.id, "journal_id": self.branch_cash.id}
        )
        offered = self.env["account.journal"].search(wizard.destination_journal_domain)

        self.assertIn(self.branch_bank, offered)
        self.assertIn(self.root_bank, offered, "the root company journals must be offered from a third-level branch")
        self.assertNotIn(self.branch_cash, offered)
        self.assertTrue(self.bundle_journals, "the root company must have its bundle journals to run this test")
        self.assertFalse(offered & self.bundle_journals)
