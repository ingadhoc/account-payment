from odoo import api, models, tools


class ResCompany(models.Model):
    _inherit = "res.company"

    def _create_payment_bundle_journal_if_needed(self):
        companies = self.filtered(lambda c: c.active and c.use_payment_pro and not c.parent_id)
        for company in companies:
            if company._get_bundle_journal("inbound"):
                continue

            template_code = company.chart_template
            if not template_code:
                continue

            chart_template = self.env["account.chart.template"].with_company(company)
            journals_to_create = chart_template._get_payment_bundle_account_journal(template_code)
            if journals_to_create:
                chart_template._load_data({"account.journal": journals_to_create})

        if companies:
            self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._create_payment_bundle_journal_if_needed()
        return companies

    def write(self, vals):
        previous_use_payment_pro = {company.id: company.use_payment_pro for company in self}
        res = super().write(vals)
        if "use_payment_pro" in vals:
            enabled_companies = self.filtered(lambda c: c.use_payment_pro and not previous_use_payment_pro.get(c.id))
            enabled_companies._create_payment_bundle_journal_if_needed()
        return res

    @tools.ormcache("self.id", "payment_type")
    def _get_bundle_journal(self, payment_type: str) -> int:
        if payment_type == "inbound":
            return (
                self.env["account.journal"]
                .search(
                    [
                        ("inbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
                        ("company_id", "=", self.id),
                    ]
                )
                .id
            )
        else:
            return (
                self.env["account.journal"]
                .search(
                    [
                        ("outbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
                        ("company_id", "=", self.id),
                    ]
                )
                .id
            )
