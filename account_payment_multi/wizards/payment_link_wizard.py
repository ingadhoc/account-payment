##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from werkzeug import urls
from odoo.exceptions import ValidationError


class PaymentLinkWizard(models.TransientModel):
    _inherit = 'payment.link.wizard'

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res_ids =  self._context.get('active_ids') 
        res_model = self._context.get('active_model')
        if len(res_ids) > 1 and  res_model == 'account.move':
            records = self.env[res_model].browse(res_ids)
            amount = sum(records.mapped('amount_residual'))
            commercial_partner_id = records.mapped('commercial_partner_id')
            if len(commercial_partner_id) != 1:
                raise ValidationError(_('Only pay invoices from the same customer.'))
            res.update({'res_ids': ','.join(map(str,res_ids)), 'partner_id': commercial_partner_id[0].id, 'amount': amount, 'amount_max':amount,})            
        return res

    res_ids = fields.Char("Related Document IDS")

    def _generate_link(self):
        for payment_link in self:
            if payment_link.res_ids:
                related_document = self.env[payment_link.res_model].browse(payment_link.res_id)
                base_url = related_document.get_base_url()  # Don't generate links for the wrong website
                payment_link.link = f'{base_url}/payment/pay' \
                    f'?reference={urls.url_quote(payment_link.description)}' \
                    f'&amount={payment_link.amount}' \
                    f'&currency_id={payment_link.currency_id.id}' \
                    f'&partner_id={payment_link.partner_id.id}' \
                    f'&company_id={payment_link.company_id.id}' \
                    f'&invoice_ids={payment_link.res_ids}' \
                    f'{"&acquirer_id=" + str(payment_link.payment_acquirer_selection) if payment_link.payment_acquirer_selection != "all" else "" }' \
                    f'&access_token={payment_link.access_token}'
            else:
                return super()._generate_link()

    def _get_additional_link_values(self):
        """ Override of `payment` to add `invoice_id` to the payment link values.

        The other values related to the invoice are directly read from the invoice.

        Note: self.ensure_one()

        :return: The additional payment link values.
        :rtype: dict
        """
        res = super()._get_additional_link_values()
        if self.res_model != 'account.move':
            return res
        if self.res_ids:
            res_ids = [int(x) for x  in self.res_ids.split(',') if x.isdigit()]
            return {
                'invoice_ids': res_ids,
            }
        return res
