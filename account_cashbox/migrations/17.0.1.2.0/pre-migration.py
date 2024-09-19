from openupgradelib import openupgrade

@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute("ALTER TABLE account_cashbox_session DROP CONSTRAINT IF EXISTS account_cashbox_session_uniq_name")
