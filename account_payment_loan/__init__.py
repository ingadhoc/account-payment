from . import models
from . import wizards


def post_init_hook(env):
    companies = env["res.company"].search([("parent_id", "=", False)])
    for company in companies:
        template_code = company.chart_template
        ChartTemplate = env["account.chart.template"].with_company(company)
        if accounts_to_create := ChartTemplate._get_personal_loan_account_account(template_code):
            ChartTemplate._load_data({"account.account": accounts_to_create})

        if journals_to_create := ChartTemplate._get_personal_loan_journal(template_code):
            ChartTemplate._load_data({"account.journal": journals_to_create})

        account_loan_journal_id = env.ref(f"account.{company.id}_account_loan_journal")
        account_loan_journal_id.default_account_id = env.ref(f"account.{company.id}_account_loan_account").id
        company.loan_journal_id = account_loan_journal_id.id
        company.account_late_payment_interest = env.ref(f"account.{company.id}_account_loan_interest_account").id
        company.account_loan_extra_charges = env.ref(f"account.{company.id}_account_loan_extra_charges").id
