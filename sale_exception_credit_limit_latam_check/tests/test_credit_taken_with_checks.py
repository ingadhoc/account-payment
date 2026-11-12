# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCreditTakenWithChecks(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.write({"group_ids": [Command.link(cls.env.ref("sale_exception_credit_limit.credit_config").id)]})
        cls.company.account_use_credit_limit = True
        if "use_payment_pro" in cls.company._fields:
            cls.company.use_payment_pro = False
        cls.partner = cls.partner_a
        # a credit limit different from the company one enables use_partner_credit_limit
        cls.partner.credit_limit = 1_000_000.0
        account_id = cls.inbound_payment_method_line.payment_account_id.id
        cls.checks_journal = cls.env["account.journal"].create(
            {
                "name": "Third Party Checks",
                "code": "TPCX",
                "type": "cash",
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(f"l10n_latam_check.account_payment_method_{code}").id,
                            "name": code,
                            "payment_account_id": account_id,
                        }
                    )
                    for code in ("new_third_party_checks", "in_third_party_checks")
                ],
            }
        )
        payment = cls.env["account.payment"].create(
            {
                "partner_id": cls.partner.id,
                "payment_type": "inbound",
                "journal_id": cls.checks_journal.id,
                "payment_method_line_id": cls.checks_journal.inbound_payment_method_line_ids.filtered(
                    lambda line: line.code == "new_third_party_checks"
                ).id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": "00001234",
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 100.0,
                        }
                    )
                ],
            }
        )
        payment.action_post()

    def _set_check_credit(self, value):
        self.env["ir.config_parameter"].sudo().set_param("l10n_latam_check_ux.add_check_credit", value)
        self.partner.invalidate_recordset(["credit_with_confirmed_orders"])

    def test_credit_taken_includes_checks_on_hand(self):
        self._set_check_credit(False)
        credit_taken = self.partner.credit_with_confirmed_orders
        self._set_check_credit(True)
        self.assertEqual(self.partner.credit_with_confirmed_orders - credit_taken, 100.0)

    def test_warning_counts_the_checks_once(self):
        """The checks reach the warning through the credit taken: adding them again on top of the
        document, as ``l10n_latam_check_ux`` does without this module, would count them twice."""
        invoice = self.init_invoice("out_invoice", partner=self.partner, amounts=[10.0])
        self._set_check_credit(False)
        total_without_checks = self.partner.credit_with_confirmed_orders + invoice.amount_total
        self._set_check_credit(True)

        # counted once the total fits, counted twice it would not
        self.partner.credit_limit = total_without_checks + 150.0
        invoice.invalidate_recordset(["partner_credit_warning"])
        self.assertFalse(invoice.partner_credit_warning)

        self.partner.credit_limit = total_without_checks + 50.0
        invoice.invalidate_recordset(["partner_credit_warning"])
        self.assertIn("checks on hand", invoice.partner_credit_warning)
        self.assertEqual(invoice.partner_credit_warning.count("checks on hand"), 1)
