# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMassTransferDestinationDomain(TransactionCase):
    """El dominio de destination_journal_id tiene que alcanzar toda la jerarquia de compañias.

    l10n_ar_payment_bundle redefine destination_journal_id con su propio dominio dinamico (para
    excluir los diarios de bundle) armado con company_id = company_id, pisando el que
    l10n_latam_check_ux corrige sobre este mismo campo (main_company_id, resuelto hasta la raiz
    del arbol). Con una jerarquia de mas de dos niveles, el desplegable quedaba vacio pese a que
    main_company_id ya apuntaba a la raiz.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = cls.env.company
        cls.branch = cls.env["res.company"].create({"name": "Branch", "parent_id": cls.root.id})
        cls.sub_branch = cls.env["res.company"].create({"name": "Sub branch", "parent_id": cls.branch.id})

        cls.root_bank_journal = cls.env["account.journal"].create(
            {
                "name": "Root Bank",
                "type": "bank",
                "code": "RBNK",
                "company_id": cls.root.id,
            }
        )

        # branches share the root company's chart of accounts, so the account is looked up there
        check_account = cls.env["account.account"].search(
            [("company_ids", "in", cls.root.id), ("account_type", "=", "asset_current")], limit=1
        )
        cls.sub_branch_check_journal = cls.env["account.journal"].create(
            {
                "name": "Sub Branch Checks",
                "type": "cash",
                "code": "SBCHK",
                "company_id": cls.sub_branch.id,
                "default_account_id": check_account.id,
            }
        )
        methods = cls.env["account.payment.method"].search(
            [("code", "in", ("new_third_party_checks", "in_third_party_checks", "out_third_party_checks"))]
        )
        for method in methods:
            field = (
                "inbound_payment_method_line_ids"
                if method.payment_type == "inbound"
                else "outbound_payment_method_line_ids"
            )
            cls.sub_branch_check_journal.write(
                {field: [Command.create({"payment_method_id": method.id, "payment_account_id": check_account.id})]}
            )

        cls.partner = cls.env["res.partner"].create({"name": "Sub Branch Customer"})
        cls.partner.with_company(cls.sub_branch).write(
            {
                "property_account_receivable_id": check_account.id,
            }
        )
        new_check_method_line = cls.sub_branch_check_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks"
        )
        payment = (
            cls.env["account.payment"]
            .with_company(cls.sub_branch)
            .create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": cls.partner.id,
                    "journal_id": cls.sub_branch_check_journal.id,
                    "payment_method_line_id": new_check_method_line.id,
                    "amount": 1000.0,
                    "l10n_latam_new_check_ids": [
                        Command.create({"name": "00000001", "payment_date": "2099-01-01", "amount": 1000.0})
                    ],
                }
            )
        )
        payment.action_post()
        cls.check = payment.l10n_latam_new_check_ids

    def test_destination_journal_domain_reaches_the_root_company(self):
        wizard = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(
                allowed_company_ids=[self.sub_branch.id, self.branch.id, self.root.id],
                active_model="l10n_latam.check",
                active_ids=self.check.ids,
            )
            .create({})
        )

        if "main_company_id" not in wizard._fields:
            self.skipTest("l10n_latam_check_ux is not installed")

        self.assertEqual(wizard.main_company_id, self.root)
        reachable = self.env["account.journal"].search(wizard.destination_journal_domain)
        self.assertIn(
            self.root_bank_journal,
            reachable,
            "the root company's bank journal should be a valid destination",
        )
