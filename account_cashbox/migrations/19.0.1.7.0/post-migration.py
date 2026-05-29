from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id in (
        "account_cashbox.cashbox_company_rule",
        "account_cashbox.cashbox_session_company_rule",
    ):
        rule = env.ref(xml_id, raise_if_not_found=False)
        if rule:
            rule.domain_force = "[('company_id', 'parent_of', company_ids)]"
