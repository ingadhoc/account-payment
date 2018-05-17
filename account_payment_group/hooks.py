# Copyright <YEAR(S)> <AUTHOR(S)>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from odoo.api import Environment
from odoo import _
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """Loaded after installing the module.
    This module's DB modifications will be available.
    :param odoo.sql_db.Cursor cr:
        Database cursor.
    :param odoo.modules.registry.Registry registry:
        Database registry, using v7 api.
    """
    Create a payment group for every existint payment
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    # payments = env['account.payment'].search(
    #     [('payment_type', '!=', 'transfer')])
    # on v10, on reconciling from statements, if not partner is choosen, then
    # a payment is created with no partner. We still make partners mandatory
    # on payment groups. So, we dont create payment groups for payments
    # without partner_id
    payments = env['account.payment'].search(
        [('partner_id', '!=', False)])

    for payment in payments:

        _logger.info('creating payment group for payment %s' % payment.id)
        env['account.payment.group'].create({
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

    if column_exists and column_exists(cr, 'res_company', 'double_validation'):
        field = 'field_res_company_double_validation'
        xmlid_renames = [(
            'account_voucher_double_validation.%s' % field,
            'account_payment_group.%s' % field),
        ]
        openupgrade.rename_xmlids(cr, xmlid_renames)

    set_user_group_for_double_validation(cr, registry)


def set_user_group_for_double_validation(cr, registry):
    """
    En v9 incorporamos un nuevo grupo para pdoer confirmar pagos, lo marcamos
    por defecto para todos los que vienen de v8 porque si tenían double
    validation no pueden hacer pagos
    """
    env = Environment(cr, 1, {})
    invoice_group = env.ref('account.group_account_invoice')
    confirm_group = env.ref('account_payment_group.account_confirm_payment')
    users = env['res.users'].search([('groups_id', '=', invoice_group.id)])
    users.write({'groups_id': [(4, confirm_group.id, None)]})


def restore_canceled_payments_state(cr, registry):
    """
    Odoo depreció el estado cancel en la v9 y lo volvió a agregar en la 11,
    nosotros hicimos un backport pero como la mig lo borra, lo tenemos que
    restaurar
    """
    env = Environment(cr, 1, {})
    # solo buscamos amount != 0.0 porque odoo borra los pagos en 0
    cr.execute("""
        SELECT partner_id, name, create_date, create_uid,
            reference, state, amount
        FROM account_voucher_copy
        WHERE state = 'cancel' and amount != 0.0
        """,)
    reads = cr.fetchall()
    for read in reads:
        (
            partner_id,
            name,
            create_date,
            create_uid,
            reference,
            state,
            amount) = read

        # como esta cancelado y no hay asiento que vincule, entonces tratamos
        # tratamos de buscar algo unico para vincular el voucher con el payment

        domain = [
            ('partner_id', '=', partner_id),
            ('create_date', '=', create_date),
            ('create_uid', '=', create_uid),
            ('payment_reference', '=', reference),
            # usamos abs porque pagos negativos se convirtieron a positivo
            ('amount', '=', abs(amount)),
            # Odoo los migra en draft
            ('state', '=', 'draft'),
        ]
        payment = env['account.payment'].search(domain)

        # si nos devuelve mas de uno intentamos agregar condición de name
        # no lo hacemos antes ya que en otros casos no sirve
        if len(payment) > 1 and name:
            domain.append(('name', '=', name))
            payment = env['account.payment'].search(domain)

        if len(payment) != 1:
            # TODO borrar, al final lo revertimos porque en realidad en cheques
            # si es necesario que sea unico para poder mapear
            # al final preferimos dar error de log y no parar upgrade por esto
            # que no es crítico
            # _logger.warning(
            #     'Se encontro mas de un payment o ninguno!!! \n'
            #     '* Payments: %s\n'
            #     '* Domain: %s' % (payment, domain))
            raise ValidationError(_(
                'Se encontro mas de un payment o ninguno!!! \n'
                '* Payments: %s\n'
                '* Domain: %s' % (payment, domain)))

        _logger.info('Cancelando payment %s' % payment)
        payment.state = 'cancel'
