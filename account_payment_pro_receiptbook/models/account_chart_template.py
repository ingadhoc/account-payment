##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    def _load(self, template_code, company, install_demo, force_create=True):
        self._create_receiptbooks(company)
        return super()._load(template_code, company, install_demo, force_create)

    @api.model
    def _create_receiptbooks(self, company):
        """
        This method can be inherited by different localizations
        """
        partner_type_name_map = {
            "customer": _("Customer Receipts"),
            "supplier": _("Supplier Payments"),
        }
        for partner_type in ["supplier", "customer"]:
            receipbook = self.env["account.payment.receiptbook"].search(
                [("partner_type", "=", partner_type), ("company_id", "=", company.id)], limit=1
            )
            if receipbook:
                continue

            document_type = self.env["l10n_latam.document.type"].search(
                [("internal_type", "=", "%s_payment" % partner_type)], limit=1
            )
            if not document_type:
                continue
            vals = {
                "name": partner_type_name_map[partner_type],
                "partner_type": partner_type,
                "company_id": company.id,
                "document_type_id": document_type.id,
                "prefix": "0001-",
            }
            # sudo() is used to bypass access restrictions during the initial creation
            # of receiptbooks when creating an argentine company,
            # as the user might not yet have access to the newly created
            # company due to multi-company rules.
            receipbook.sudo().create(vals)
