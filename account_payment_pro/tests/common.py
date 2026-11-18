# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import Form


class PaymentProCommon(AccountTestInvoicingCommon):
    """A company with payment pro on, and the forms the tests fill in."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.use_payment_pro = True
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _payment_form(self, partner=None, journal=None, **context):
        form = Form(self.env["account.payment"].with_context(**context))
        form.journal_id = journal or self.bank_journal
        if partner:
            form.partner_id = partner
        return form

    def _supplier_payment_form(self, partner=None, journal=None):
        return self._payment_form(partner, journal, default_partner_type="supplier", default_payment_type="outbound")

    def _receipt_form(self, partner=None, journal=None):
        return self._payment_form(partner, journal, default_partner_type="customer", default_payment_type="inbound")


class WithholdingCommon(PaymentProCommon):
    """...plus the withholding taxes and the account their base books to."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_account = cls.env["account.account"].create(
            {"code": "WITHB", "name": "Withholding Tax Base", "account_type": "asset_current"}
        )
        cls.company.withholding_tax_base_account_id = cls.base_account
        cls.withholding_tax, cls.sale_withholding_tax, cls.withholding_tax_3 = cls.env["account.tax"].create(
            [
                {
                    "name": "Withholding 2%",
                    "amount_type": "percent",
                    "amount": -2.0,
                    "type_tax_use": "purchase",
                    "is_withholding_tax": True,
                },
                {
                    "name": "Suffered withholding 2%",
                    "amount_type": "percent",
                    "amount": -2.0,
                    "type_tax_use": "sale",
                    "is_withholding_tax": True,
                },
                {
                    "name": "Withholding 3%",
                    "amount_type": "percent",
                    "amount": -3.0,
                    "type_tax_use": "purchase",
                    "is_withholding_tax": True,
                },
            ]
        )

    def _payment(self, withholding_base=1000.0, tax=None, withholdings=None, **vals):
        """A draft supplier payment of 1000 with one withholding over ``withholding_base``.

        ``withholdings`` takes (tax, base amount) pairs instead, for the payments with more than one.
        """
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "journal_id": self.bank_journal.id,
                "amount": 1000.0,
                **vals,
            }
        )
        if withholdings is None and withholding_base:
            withholdings = [(tax or self.withholding_tax, withholding_base)]
        if withholdings:
            payment.withholding_line_ids = [
                Command.create({"tax_id": line_tax.id, "base_amount": base}) for line_tax, base in withholdings
            ]
        return payment

    def _add_withholding(self, form, base_amount, tax=None):
        with form.withholding_line_ids.new() as line:
            line.tax_id = tax or self.withholding_tax
            line.base_amount = base_amount

    def _base_lines(self, payment):
        """The base journal items of the withholdings, without their tax lines."""
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.base_account and not line.tax_repartition_line_id
        )
