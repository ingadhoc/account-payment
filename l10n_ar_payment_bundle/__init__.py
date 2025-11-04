from . import models


def post_init_hook(env):
    """Existing companies that have the Argentinean Chart of Accounts set"""
    ar_companies = env["res.company"].search([("parent_id", "=", False)]).filtered(lambda x: x.country_code == "AR")
    for company in ar_companies:
        ChartTemplate = env["account.chart.template"].with_company(company)
        if journals_to_create := ChartTemplate._get_payment_bundle_account_journal(company.chart_template):
            ChartTemplate._load_data({"account.journal": journals_to_create})
