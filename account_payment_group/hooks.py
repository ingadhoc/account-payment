# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from openerp import api, SUPERUSER_ID
_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """
    Create a payment group for every existint payment
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    payments = env['account.payment'].search(
        [('payment_type', '!=', 'transfer')])

    for payment in payments:

        _logger.info('creating payment group for payment %s' % payment.id)
        registry['account.payment.group'].create(cr, 1, {
            'company_id': payment.company_id.id,
            'partner_type': payment.partner_type,
            'partner_id': payment.partner_id.id,
            'payment_date': payment.payment_date,
            # en realidad aparentemente odoo no migra nada a communication
            # tal vez a este campo deberíamos llevar el viejo name que ahora
            # name es la secuencia
            'communication': payment.communication,
            'payment_ids': [(4, payment.id, False)],
            'state': (
                payment.state in ['sent', 'reconciled'] and
                'posted' or payment.state),
        })
