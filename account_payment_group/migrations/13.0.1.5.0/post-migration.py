from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(
        env.cr, 'account_payment_group',
        'migrations/13.0.1.5.0/mig_data.xml')
