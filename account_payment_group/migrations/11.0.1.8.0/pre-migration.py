from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(
        env.cr, 'account_payment_group',
        'migrations/11.0.1.8.0/mig_data.xml')
