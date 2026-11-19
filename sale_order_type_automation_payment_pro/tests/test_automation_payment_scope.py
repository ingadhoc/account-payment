from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestAutomationPaymentScope(AccountTestInvoicingCommon):
    @classmethod
    def setup_independent_user(cls):
        return None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.use_payment_pro = True
        cls.payment_journal = cls.company_data["default_journal_bank"]
        cls.sale_type = cls.env["sale.order.type"].create(
            {
                "name": "Test Automation Payment Scope",
                "company_id": cls.env.company.id,
                "payment_atomation": "validate_payment",
                "payment_journal_id": cls.payment_journal.id,
            }
        )

    def test_automatic_payment_reconciles_the_flow_invoice(self):
        """With a prior open invoice, the automatic payment pays the invoice of the flow, not the old debt."""
        old_invoice = self._create_invoice_one_line(price_unit=300.0, tax_ids=[], post=True)
        invoice = self._create_invoice_one_line(price_unit=100.0, tax_ids=[], sale_type_id=self.sale_type)

        invoice.action_post()

        payment = invoice.reconciled_payment_ids
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.to_pay_move_line_ids.move_id, invoice)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(invoice.payment_state, "paid")
        self.assertEqual(old_invoice.amount_residual, 300.0)
        self.assertEqual(old_invoice.payment_state, "not_paid")
