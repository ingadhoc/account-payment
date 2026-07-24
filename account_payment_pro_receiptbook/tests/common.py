from odoo.addons.account_payment_pro.tests.common import PaymentProCommon


class ReceiptbookCommon(PaymentProCommon):
    """PaymentProCommon plus receiptbooks enabled on the test company.

    The receiptbooks themselves are module data created when
    ``use_receiptbook`` is enabled, so there is no extra demo to install.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.use_receiptbook = True
        cls.receiptbook = cls.env["account.payment.receiptbook"].search(
            [("company_id", "=", cls.company.id), ("name", "=", "Customer Receipts")]
        )
