import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


# pylint: disable=consider-merging-classes-inherited
# pylint: disable=R8180
class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @api.model
    def _install_account_payment_pro_demo(self, companies=None):
        """Load account_payment_pro demo data for the given companies.

        Idempotent: xml_ids are company-prefixed by ``_load_data``
        (``account.<company_id>_<xml_id>``) and stored with noupdate, so
        calling it again (e.g. from a test setUpClass) does not duplicate
        records. Reusable from tests via ``PaymentProCommon``.
        """
        for company in companies if companies is not None else self.env.company:
            _logger.info("Creating account_payment_pro demo data for company %s", company.name)
            template = self.with_company(company).sudo()
            data = template._account_payment_pro_demo_data()
            for journal_vals in data["account.journal"].values():
                journal_vals["company_id"] = company.id
            template._load_data(data)

    @api.model
    def _account_payment_pro_demo_data(self):
        """Demo records, mapping {model: {xml_id: values}} for ``_load_data``."""
        return {
            "res.partner": {
                "demo_partner_ri": {
                    "name": "RI Partner (demo)",
                    "vat": "34278580484",
                    "country_id": "base.ar",
                },
            },
            "product.product": {
                "demo_product": {
                    "name": "Payment Pro Demo Service",
                    "type": "service",
                    "list_price": 100.0,
                },
            },
            "account.journal": {
                "demo_bank_journal": {
                    "name": "Demo Bank",
                    "type": "bank",
                    "code": "DBNK",
                },
                "demo_sale_journal": {
                    "name": "Demo Sales",
                    "type": "sale",
                    "code": "DSALE",
                    "l10n_latam_use_documents": False,
                },
                "demo_purchase_journal": {
                    "name": "Demo Purchases",
                    "type": "purchase",
                    "code": "DPUR",
                    "l10n_latam_use_documents": False,
                },
            },
        }
