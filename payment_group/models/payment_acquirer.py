# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields


class PaymentAcquirer(models.Model):
    _inherit = "payment.acquirer"

    only_published_for_group_ids = fields.Many2many(
        'res.groups',
        'payment_acquirer_group_rel',
        'acquirer_id', 'group_id',
        string='Only Published for Groups',
        help='Set which groups are allowed to use this payment acquirer. If no'
        ' group specified this payment option will be available for everybody'
    )

    # no pudimos hacerlo andar con la nueva api!
    def render(
        self, cr, uid, id, reference, amount, currency_id,
            partner_id=False, values=None, context=None):
        """
        We can not use security because the render of button in website is
        called with superuser
        TODO: not sure why it dont works in new api
        NOTA: este metodo no devuelve lo permitido por el usuario logueado
        si no mas bien lo relativo al partner, por ej, viendo una orden de
        venta, por mas que sea super admin, solo veo segun permiso del
        partner de la orden de venta
        """
        acquirer = self.browse(cr, uid, id)
        if acquirer.only_published_for_group_ids:
            # if no partner_id then he can not see
            if not partner_id:
                return False
            # this function is called with super admin, so we need to get
            # user from partner_id but looking for inactive users too
            user_ids = self.pool['res.users'].search(cr, uid, [
                ('partner_id', '=', partner_id),
                ('active', 'in', [True, False])], context=context)
            # if no user found we use public user
            if not user_ids:
                user_ids = [self.pool['ir.model.data'].xmlid_to_res_id(
                    cr, uid, 'base.public_user')]

            # check if there is a match between users and groups required
            groups_ids = self.pool['res.groups'].search(cr, uid, [
                ('users', 'in', user_ids),
                ('id', 'in', acquirer.only_published_for_group_ids.ids)],
                context=context)
            if not groups_ids:
                return False
        return super(PaymentAcquirer, self).render(
            cr, uid, id, reference, amount, currency_id, partner_id=partner_id,
            values=values, context=context)
