# -*- coding: utf-8 -*-
# Copyright <YEAR(S)> <AUTHOR(S)>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
try:
    from openupgradelib.openupgrade_tools import column_exists
    from openupgradelib import openupgrade
except ImportError:
    column_exists = None
    openupgrade = None
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

    restore_canceled_payments_state(cr, registry)

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

    if column_exists and column_exists(cr, 'res_company', 'double_validation'):
        field = 'field_res_company_double_validation'
        xmlid_renames = [(
            'account_voucher_double_validation.%s' % field,
            'account_payment_group.%s' % field),
        ]
        openupgrade.rename_xmlids(cr, xmlid_renames)


def restore_canceled_payments_state(cr, registry):
    """
    Odoo depreció el estado cancel en la v9 y lo volvió a agregar en la 11,
    nosotros hicimos un backport pero como la mig lo borra, lo tenemos que
    restaurar
    """
    cr.execute("""
        SELECT partner_id, name, create_date, create_uid, reference
        FROM account_voucher_copy
        WHERE state = 'cancel'
        """,)
    reads = cr.fetchall()
    for read in reads:
        (
            partner_id,
            name,
            create_date,
            create_uid,
            reference) = read
        # al final no buscamos por name porque si no estaba setado odoo
        # completa con otra cosa
        # ('name', '=', name),
        domain = [
            ('partner_id', '=', partner_id),
            ('create_date', '=', create_date), ('create_uid', '=', create_uid),
            ('payment_reference', '=', reference)]
        payment_id = registry['account.payment'].search(
            cr, 1, domain, limit=1)
        if not payment_id:
            _logger.error(
                'No encontramos payment para cancelar con dominio %s' % (
                    domain))
            continue
        _logger.info('Cancelando payment %s' % payment_id)
        registry['account.payment'].write(
            cr, 1, payment_id, {'state': 'cancel'})
