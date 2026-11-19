# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
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
