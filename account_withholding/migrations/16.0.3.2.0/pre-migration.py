from openupgradelib import openupgrade
import logging
logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):

    logger.info('Forzamos la actualización de la vista de account_move_views en módulo account para que pueda aplicarse correctamente este cambio https://github.com/odoo/odoo/pull/240659')
    openupgrade.load_data(env.cr, 'account', 'views/account_move_views.xml')
