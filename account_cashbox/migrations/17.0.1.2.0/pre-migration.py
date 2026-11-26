from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.cr.execute("ALTER TABLE account_cashbox_session DROP CONSTRAINT IF EXISTS account_cashbox_session_uniq_name")
