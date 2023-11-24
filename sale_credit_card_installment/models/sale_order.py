##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_open_payment_wizard(self):
        view_id = self.env.ref('sale_credit_card_installment.choose_payment_view_form').id
        # if self.env.context.get('carrier_recompute'):
        #     name = _('Update shipping cost')
        #     carrier = self.carrier_id
        # else:
        #     name = _('Add a shipping method')
        #     carrier = (
        #             self.with_company(self.company_id).partner_shipping_id.property_delivery_carrier_id
        #             or self.with_company(
        #         self.company_id).partner_shipping_id.commercial_partner_id.property_delivery_carrier_id
        #     )
        return {
            'name': 'Método de pago',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'choose.payment.method',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                # 'default_carrier_id': carrier.id,
            }
        }
