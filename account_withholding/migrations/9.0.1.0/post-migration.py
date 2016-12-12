# -*- coding: utf-8 -*-
from openupgradelib import openupgrade


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    env['account.journal']._enable_withholding_on_cash_journals()
    migrate_tax_withholding(env)


def migrate_tax_withholding(env):
    cr = env.cr
    openupgrade.logged_query(cr, """
    SELECT
        name,
        description,
        type_tax_use,
        active,
        account_id,
        ref_account_id,
        ref_account_analytic_id,
        company_id,
        type_tax_use,
        tax_code_id
    FROM
        account_tax_withholding
    """,)
    for tax_read in cr.fetchall():
        (
            name,
            description,
            type_tax_use,
            active,
            account_id,
            ref_account_id,
            ref_account_analytic_id,
            company_id,
            type_tax_use,
            tax_code_id) = tax_read

        # get tax_group from tax code
        # TODO improove, use "using and get tax_group" we should also
        # update this module later than l10n_ar_account or do this changes
        # on l10n_ar_account
        # openupgrade.logged_query(cr, """
        # SELECT
        #     tax,
        #     type,
        #     application
        # FROM
        #     account_tax_code
        # WHERE
        #     id = %s
        # """, (tax_code_id,))

        tax_vals = {
            'name': name,
            'description': description,
            'active': description,
            'account_id': account_id,
            'refund_account_id': ref_account_id,
            'company_id': company_id,
            'amount_type': 'fixed',
            # TODO type all not implemented, we should duplicate tax
            'type_tax_use': (
                type_tax_use == 'receipt' and 'customer' or 'supplier'),
            # 'tax_group_id': False,
            'amount': 0.0,
        }
        env['account.tax'].create(tax_vals)
