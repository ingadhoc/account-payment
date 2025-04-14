from odoo import Command, _, models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template(model="account.journal")
    def _get_payment_bundle_account_journal(self, template_code):
        if self.env.company.country_code == "AR" and template_code in ["ar_ri", "ar_ex", "ar_base"]:
            return {
                "payment_bundle_journal": {
                    "name": _("Multiple payments"),
                    "type": "cash",
                    "outbound_payment_method_line_ids": [
                        Command.create(
                            {
                                "payment_method_id": self.env.ref(
                                    "l10n_ar_payment_bundle.account_payment_out_payment_bundle"
                                ).id,
                            }
                        ),
                    ],
                    "inbound_payment_method_line_ids": [
                        Command.create(
                            {
                                "payment_method_id": self.env.ref(
                                    "l10n_ar_payment_bundle.account_payment_in_payment_bundle"
                                ).id,
                            }
                        ),
                    ],
                },
            }
