from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute("update account_tax set amount = 0.0 where amount is null")
