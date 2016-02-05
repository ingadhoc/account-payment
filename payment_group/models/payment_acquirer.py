# -*- coding: utf-8 -*-
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

    def render(
            self, cr, uid, id, reference, amount, currency_id, tx_id=None,
            partner_id=False, partner_values=None, tx_values=None,
            context=None):
        """
        We can not use security because the render of button in website is
        called with superuser
        TODO: not sure why it dont works in new api
        """
        acquirer = self.browse(cr, uid, id)
        if acquirer.only_published_for_group_ids:
            # if no partner_id then he can not see
            if not partner_id:
                return False

            partner_group_ids = self.pool['res.groups'].search(cr, uid, [
                ('users.partner_id', '=', partner_id),
                ], context=context)
            if not set(partner_group_ids).intersection(
                    acquirer.only_published_for_group_ids.ids):
                return False
        return super(PaymentAcquirer, self).render(
            cr, uid, id, reference, amount, currency_id, tx_id=tx_id,
            partner_id=partner_id, partner_values=partner_values,
            tx_values=tx_values, context=context)
