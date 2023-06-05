from openupgradelib import openupgrade
import logging
logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    env['account.move.line'].search([('tax_repartition_line_id', '!=', False), ('create_date', '>', '2023-01-1'), ('tax_state', '=', False)])._compute_tax_state()
    logger.info('Se computaron campos tax_repartition_line_id y tax_line_id en líneas de retenciones ya publicadas')
