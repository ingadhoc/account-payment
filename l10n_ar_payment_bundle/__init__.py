from . import models


def post_init_hook(env):
    """Existing companies that have the Argentinean Chart of Accounts set"""
    ar_companies = env["res.company"].search([("partner_id.country_id.code", "=", "AR"), ("parent_id", "=", False)])
    for company in ar_companies:
        template_code = company.chart_template
        ChartTemplate = env["account.chart.template"].with_company(company)
        if journals_to_create := ChartTemplate._get_payment_bundle_account_journal(template_code):
            ChartTemplate._load_data({"account.journal": journals_to_create})
