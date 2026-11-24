# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestRateDirection(AccountTestInvoicingCommon):
    """The form asks for the rate as "1 foreign = X company", also when the base has no rate for the date.

    Without one the theoretical rate comes back as 1.0 and the direction used to fall on the wrong side, so a
    user typing 1.000 got the amount multiplied by a thousand instead of divided.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.use_payment_pro = True
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.no_rate_currency = (
            cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "XTS")], limit=1)
        )
        if not cls.no_rate_currency:
            cls.no_rate_currency = cls.env["res.currency"].create({"name": "XTS", "symbol": "XT"})
        cls.no_rate_currency.active = True
        cls.env["res.currency.rate"].search([("currency_id", "=", cls.no_rate_currency.id)]).unlink()

    def _receipt_form(self, partner=None, journal=None):
        form = Form(
            self.env["account.payment"].with_context(
                default_partner_type="customer",
                default_payment_type="inbound",
            )
        )
        form.journal_id = journal or self.bank_journal
        if partner:
            form.partner_id = partner
        return form

    def _invoice_without_a_rate(self, amount=100.0, currency=None):
        return self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            amounts=[amount],
            taxes=[],
            currency=currency or self.no_rate_currency,
            post=True,
        )

    def test_the_rate_of_a_debt_without_a_rate_is_asked_the_right_way_round(self):
        invoice = self._invoice_without_a_rate()
        form = self._receipt_form(invoice.partner_id)

        self.assertEqual(form.currency_id, self.company.currency_id, "the payment is in the currency of the journal")
        self.assertEqual(form.counterpart_currency_id, self.no_rate_currency)
        self.assertTrue(
            form.counterpart_rate_inverted,
            'the form asks "1 XTS = X company currency", not the other way round',
        )

    def test_the_rate_the_user_types_divides_the_amount(self):
        invoice = self._invoice_without_a_rate()
        form = self._receipt_form(invoice.partner_id)

        form.user_counterpart_rate = 1000.0
        form.amount = 100000.0

        self.assertEqual(form.counterpart_currency_amount, 100.0, "100.000 at 1.000 are 100, not 100 million")

    def test_a_foreign_journal_without_a_rate_asks_for_the_company_currency(self):
        foreign_journal = self.env["account.journal"].create(
            {
                "name": "Bank XTS",
                "type": "bank",
                "code": "BXTS",
                "company_id": self.company.id,
                "currency_id": self.no_rate_currency.id,
            }
        )
        self.init_invoice("out_invoice", partner=self.partner_a, amounts=[180000.0], taxes=[], post=True)
        form = self._receipt_form(self.partner_a, journal=foreign_journal)

        self.assertEqual(form.currency_id, self.no_rate_currency)
        self.assertTrue(
            form.accounting_rate_inverted,
            'the form asks "1 XTS = X company currency"',
        )

        form.user_accounting_rate = 1000.0
        form.amount = 180.0

        self.assertEqual(form.counterpart_currency_amount, 180000.0, "180 at 1.000 are 180.000, not 0,18")

    def test_typing_the_debt_currency_amount_settles_both(self):
        invoice = self._invoice_without_a_rate()
        form = self._receipt_form(invoice.partner_id)
        form.user_counterpart_rate = 1000.0

        form.counterpart_currency_amount = 100.0

        self.assertEqual(form.amount, 100000.0, "the amount in the journal currency follows the debt")
        self.assertEqual(form.counterpart_currency_amount, 100.0, "and the debt currency amount stays where it was")
        self.assertEqual(form.payment_difference, 0.0, "so the debt can actually be settled")
