##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.tests import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestChecksToDateReport(LatamCheckCommon):
    """The report lists exactly the companies selected in the company switcher."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env["res.company"].create({"name": "Report Branch", "parent_id": cls.company.id})
        # the branch shares the parent chart of accounts, but the company dependent
        # properties of the partner have to be set for it to post payments there
        cls.partner.with_company(cls.branch).write(
            {
                "property_account_receivable_id": cls.receivable_account.id,
                "property_account_payable_id": cls.destination_account.id,
            }
        )
        cls.branch_bank_journal = cls.env["account.journal"].create(
            {"name": "Branch Checks Bank", "code": "BCHKB", "type": "bank", "company_id": cls.branch.id}
        )
        cls.branch_own_checks_line = cls._add_method_line(
            cls.branch_bank_journal, cls.own_checks_method, "Own Checks", cls.deferred_check_account
        )
        cls.branch_third_party_journal = cls.env["account.journal"].create(
            {"name": "Branch Third Party Checks", "code": "BTPC", "type": "cash", "company_id": cls.branch.id}
        )
        cls.branch_new_third_party_line = cls._add_method_line(
            cls.branch_third_party_journal,
            cls.new_third_party_method,
            "New Third Party Checks",
            cls.third_party_account,
        )

    def _post_check_payment(self, method_line, payment_type, number):
        company = method_line.journal_id.company_id
        payment = (
            self.env["account.payment"]
            .with_company(company)
            .create(
                {
                    "payment_type": payment_type,
                    "partner_type": "supplier" if payment_type == "outbound" else "customer",
                    "partner_id": self.partner.id,
                    "journal_id": method_line.journal_id.id,
                    "company_id": company.id,
                    "date": self.today,
                    "payment_method_line_id": method_line.id,
                    "l10n_latam_new_check_ids": [
                        Command.create(self._new_check_vals(100, number, issuer=payment_type == "inbound"))
                    ],
                }
            )
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _setup_checks(self):
        checks = {
            "root_own": self._post_check_payment(self.own_checks_line, "outbound", "00020001"),
            "branch_own": self._post_check_payment(self.branch_own_checks_line, "outbound", "00020002"),
            "root_third": self._post_check_payment(self.new_third_party_line, "inbound", "00020003"),
            "branch_third": self._post_check_payment(self.branch_new_third_party_line, "inbound", "00020004"),
        }
        # the report reads with raw SQL: the stored computed fields of the checks have to be in the database
        self.env.flush_all()
        return checks

    def _wizard(self, companies):
        return (
            self.env["account.check.to_date.report.wizard"]
            .with_context(allowed_company_ids=companies.ids)
            .create({"to_date": self.today})
        )

    def _render(self, wizard):
        html, _ = (
            self.env["ir.actions.report"]
            .with_context(allowed_company_ids=wizard.env.companies.ids)
            ._render_qweb_html("l10n_latam_check_ux.checks_to_date_report", wizard.ids)
        )
        return html.decode()

    def test_report_includes_every_selected_company(self):
        """Dos compañías tildadas: salen los cheques de las dos, cada uno con su compañía.

        La activa es la sucursal y la otra tildada es su padre: el reporte no se limita
        al árbol de la compañía activa.
        """
        checks = self._setup_checks()
        wizard = self._wizard(self.branch | self.company)

        self.assertEqual(wizard.company_ids, self.branch | self.company)
        handed = wizard._get_checks_handed(False, self.today)
        on_hand = wizard._get_checks_on_hand(False, self.today)
        self.assertEqual(
            handed & (checks["root_own"] | checks["branch_own"]), checks["root_own"] | checks["branch_own"]
        )
        self.assertEqual(
            on_hand & (checks["root_third"] | checks["branch_third"]), checks["root_third"] | checks["branch_third"]
        )
        self.assertEqual(checks["branch_own"].company_id, self.branch)
        self.assertEqual(checks["branch_third"].company_id, self.branch)

        html = self._render(wizard)
        self.assertIn(">Compañía</th>", html, "with more than one company each check shows its company")
        self.assertIn(self.branch.name, html)

    def test_report_excludes_unselected_company(self):
        """Una sola compañía tildada: no salen los cheques propios ni de terceros de la otra."""
        checks = self._setup_checks()
        wizard = self._wizard(self.company)

        handed = wizard._get_checks_handed(False, self.today)
        on_hand = wizard._get_checks_on_hand(False, self.today)
        self.assertIn(checks["root_own"], handed)
        self.assertNotIn(checks["branch_own"], handed)
        self.assertIn(checks["root_third"], on_hand)
        self.assertNotIn(checks["branch_third"], on_hand)

        html = self._render(wizard)
        self.assertNotIn(">Compañía</th>", html, "a single company report has no company column")
