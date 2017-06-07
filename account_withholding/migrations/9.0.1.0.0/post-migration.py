# -*- coding: utf-8 -*-
from openupgradelib import openupgrade


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    # al final usamos diario separado
    # env['account.journal']._enable_withholding_on_cash_journals()
    migrate_tax_withholding(env)
    create_withholding_journal(env)


def create_withholding_journal(env):
    # creamos diario para retenciones
    for company in env['res.company'].search([]):
        inbound_withholding = env.ref(
            'account_withholding.account_payment_method_in_withholding')
        outbound_withholding = env.ref(
            'account_withholding.account_payment_method_out_withholding')
        journal = env['account.journal'].create({
            'name': 'Retenciones',
            'type': 'cash',
            'company_id': company.id,
            'inbound_payment_method_ids': [
                (4, inbound_withholding.id, None)],
            'outbound_payment_method_ids': [
                (4, outbound_withholding.id, None)],
        })
        # we dont want this journal to have accounts and we can not inherit
        # to avoid creation, so we delete it
        journal.default_credit_account_id.unlink()


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
        new_tax = env['account.tax'].create(tax_vals)
        # we add tax_code_id by sql because it is a column but not a field
        # we add this so l10n_ar_account postinstall script can map tax group
        if tax_code_id:
            openupgrade.logged_query(cr, """
            UPDATE account_tax set tax_code_id = %s where id = %s
            """ % (tax_code_id, new_tax.id))
