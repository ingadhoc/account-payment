# -*- coding: utf-8 -*-
# Copyright <YEAR(S)> <AUTHOR(S)>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
try:
    from openupgradelib.openupgrade_tools import table_exists
except ImportError:
    table_exists = None
import logging
_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """Loaded after installing the module.
    This module's DB modifications will be available.
    :param openerp.sql_db.Cursor cr:
        Database cursor.
    :param openerp.modules.registry.RegistryManager registry:
        Database registry, using v7 api.
    """
    _logger.info('running payment')
    payment_ids = registry['account.payment'].search(
        cr, 1, [('payment_type', '!=', 'transfer')])
    for payment in registry['account.payment'].browse(cr, 1, payment_ids):
        _logger.info('creating payment group for payment %s' % payment.id)
        registry['account.payment.group'].create(cr, 1, {
            'company_id': payment.company_id.id,
            'partner_type': payment.partner_type,
            'partner_id': payment.partner_id.id,
            'payment_date': payment.payment_date,
            'communication': payment.communication,
            'payment_ids': [(4, payment.id, False)],
            'state': (
                payment.state in ['sent', 'reconciled'] and
                'posted' or payment.state),
        })
