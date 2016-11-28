# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
import logging
from openerp import pooler, SUPERUSER_ID
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info(
        'Running post migrate of voucher withholding from version %s' % version)
    # cr.execute(
    #     "update account_check set owner_name='/'")
    pool = pooler.get_pool(cr.dbname)
    compute_net_amounts(cr, pool)


def compute_net_amounts(cr, pool):
    withholding_obj = pool['account.voucher.withholding']
    withholding_ids = withholding_obj.search(
            cr, SUPERUSER_ID, [('withholdable_base_amount', '!=', False)], {})
    _logger.info('Computing base_amount for withholdings %s' % withholding_ids)
    for withholding_id in withholding_ids:
        base_amount = withholding_obj.read(
            cr, SUPERUSER_ID, withholding_id, ['withholdable_base_amount'])['withholdable_base_amount']
        withholding_obj.write(
            cr, SUPERUSER_ID, withholding_id, {'base_amount': base_amount})
