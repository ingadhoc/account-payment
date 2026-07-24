from odoo.tests import tagged

from .common import PaymentProCommon


@tagged("post_install", "-at_install")
class TestPaymentProDemoData(PaymentProCommon):
    def test_install_demo_idempotent(self):
        """A second install must not duplicate records nor xml_ids."""
        self.chart_template._install_account_payment_pro_demo(self.company)
        count = self.env["ir.model.data"].search_count(
            [("module", "=", "account"), ("name", "=", f"{self.company.id}_demo_partner_ri")]
        )
        self.assertEqual(count, 1, "el xml_id de la demo se duplicó en ir.model.data")
        self.assertEqual(self.chart_template.ref("demo_partner_ri"), self.partner_ri)
