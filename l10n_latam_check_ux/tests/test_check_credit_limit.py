# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCheckCreditLimit(AccountTestInvoicingCommon):
    """Third party checks on hand in the credit limit warning (task 52412)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.account_use_credit_limit = True
        if "use_payment_pro" in cls.company._fields:
            cls.company.use_payment_pro = False
        # with sale_exception_credit_limit installed only this group can set a credit limit
        if credit_config := cls.env.ref("sale_exception_credit_limit.credit_config", raise_if_not_found=False):
            cls.env.user.write({"groups_id": [Command.link(credit_config.id)]})
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

    def _receive_check(self, number, partner=None, currency=None, payment_date=None):
        payment = self.env["account.payment"].create(
            {
                "partner_id": (partner or self.partner_a).id,
                "payment_type": "inbound",
                "journal_id": self.checks_journal.id,
                "currency_id": (currency or self.company.currency_id).id,
                "payment_method_line_id": self.checks_journal.inbound_payment_method_line_ids.filtered(
                    lambda line: line.code == "new_third_party_checks"
                ).id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": number,
                            "payment_date": payment_date or fields.Date.add(fields.Date.today(), months=1),
                            "amount": 100.0,
                        }
                    )
                ],
            }
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _set_check_credit(self, value):
        self.env["ir.config_parameter"].sudo().set_param("l10n_latam_check_ux.add_check_credit", value)
        # the computes reading it (e.g. the credit taken of sale_exception_credit_limit) are not stored
        self.env.invalidate_all()

    def _checks_credit(self):
        return self.partner_a._get_on_hand_checks_credit(self.company)

    def test_credit_limit_warning_includes_checks_on_hand(self):
        """Checks on hand, due or not, go into the credit limit warning, never into ``credit``."""
        self._receive_check("00005201")
        self._receive_check("00005202", payment_date=fields.Date.today())
        invoice = self.init_invoice("out_invoice", partner=self.partner_a, amounts=[10.0])
        partner = self.partner_a.with_company(self.company)
        credit = partner.credit
        # the invoice alone fits in the limit, the invoice plus the checks on hand do not
        partner.credit_limit = credit + invoice.amount_total + 150.0

        self._set_check_credit(False)
        self.assertFalse(invoice.partner_credit_warning, "Without the setting the checks are ignored")
        self.assertEqual(self._checks_credit(), 0.0)

        self._set_check_credit(True)
        self.assertEqual(self._checks_credit(), 200.0, "Due or not, both checks are on hand")
        self.assertIn("checks on hand", invoice.partner_credit_warning)
        self.assertEqual(partner.credit, credit, "Checks never touch the accounting debt")

    def test_check_credit_of_contacts_goes_to_commercial_partner(self):
        self._set_check_credit(True)
        contact = self.env["res.partner"].create({"name": "Contact", "parent_id": self.partner_a.id})
        self._receive_check("00005203", partner=contact)
        self.assertEqual(self._checks_credit(), 100.0)

    def test_check_credit_in_foreign_currency(self):
        self._set_check_credit(True)
        currency = self.setup_other_currency("EUR", rates=[(fields.Date.to_string(fields.Date.today()), 0.001)])
        self._receive_check("00005204", currency=currency)
        self.assertAlmostEqual(self._checks_credit(), 100_000.0)
