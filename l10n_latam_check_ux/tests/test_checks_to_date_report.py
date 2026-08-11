##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestChecksToDateReportCompanies(LatamCheckCommon):
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
        branch_third_party_journal = cls.env["account.journal"].create(
            {"name": "Branch Third Party Checks", "code": "BTPC", "type": "cash", "company_id": cls.branch.id}
        )
        cls.branch_new_third_party_line = cls._add_method_line(
            branch_third_party_journal, cls.new_third_party_method, "New Third Party Checks", cls.third_party_account
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

    def _wizard(self, companies):
        return (
            self.env["account.check.to_date.report.wizard"]
            .with_context(allowed_company_ids=companies.ids)
            .create({"to_date": self.today})
        )

    def test_report_lists_the_selected_companies(self):
        """Salen los cheques propios y de terceros de las compañías tildadas, y solo de esas.

        La activa es la sucursal y la otra tildada es su padre: el reporte no se limita al
        árbol de la compañía activa. Con más de una compañía, el PDF trae la columna Compañía.
        """
        root_own = self._post_check_payment(self.own_checks_line, "outbound", "00020001")
        branch_own = self._post_check_payment(self.branch_own_checks_line, "outbound", "00020002")
        root_third = self._post_check_payment(self.new_third_party_line, "inbound", "00020003")
        branch_third = self._post_check_payment(self.branch_new_third_party_line, "inbound", "00020004")
        own, third = root_own | branch_own, root_third | branch_third
        # the report reads with raw SQL: the stored computed fields of the checks have to be in the database
        self.env.flush_all()

        for label, companies, expected_own, expected_third, has_column in [
            ("dos compañías tildadas", self.branch | self.company, own, third, True),
            ("solo la casa central", self.company, root_own, root_third, False),
        ]:
            with self.subTest(label):
                wizard = self._wizard(companies)
                self.assertEqual(wizard._get_checks_handed(False, self.today) & own, expected_own)
                self.assertEqual(wizard._get_checks_on_hand(False, self.today) & third, expected_third)
                html = (
                    self.env["ir.actions.report"]
                    .with_context(allowed_company_ids=companies.ids)
                    ._render_qweb_html("l10n_latam_check_ux.checks_to_date_report", wizard.ids)[0]
                    .decode()
                )
                self.assertEqual(">Compañía</th>" in html, has_column)

    def test_journal_options(self):
        """El diario se elige entre los de las compañías tildadas y los de sus casas centrales,
        incluidos los bancos con chequera."""

        def options(companies):
            wizard = self._wizard(companies)
            # evaluate the field domain the same way the web client does
            domain = safe_eval(wizard._fields["journal_id"].domain, {"company_ids": wizard.company_ids.ids})
            return wizard.env["account.journal"].search(domain)

        branch_options = options(self.branch)
        self.assertIn(self.branch_bank_journal, branch_options, "own checks journals are offered")
        self.assertIn(self.bank_journal, branch_options, "the parent company journals are offered")
        self.assertNotIn(self.branch_bank_journal, options(self.company), "a branch journal needs the branch selected")
