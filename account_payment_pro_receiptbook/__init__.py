from . import models


def _generate_receiptbooks(env):
    """ Create receiptbooks on existing companies with chart installed"""
    with_chart_companies = env['res.company'].search([('chart_template', '!=', False)])
    for company in with_chart_companies:
        env['account.chart.template']._create_receiptbooks(company)
