##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.http import request

from odoo.addons.portal.controllers import portal
from odoo.tools import float_compare


class PaymentPortal(portal.CustomerPortal):

    @http.route('/payment/invoice_multi_link', type='json', auth='user')
    def invoice_multi_transaction(self, invoice_ids, amount, **kwargs):
        invoices_sudo = request.env['account.move'].sudo()
        for invoice in invoice_ids:
            # Check the invoice id
            invoices_sudo += self._document_check_access('account.move', invoice['id'], invoice.get('token'))
        payment_link = request.env['payment.link.wizard'].sudo().with_context(active_id=invoices_sudo[0].id, active_ids=invoices_sudo.ids, active_model='account.move').create({})

        if float_compare(payment_link.amount_max, amount, precision_rounding=payment_link.currency_id.rounding or 0.01) == -1:
            raise ValidationError(_("Incorrect amount"))
        return payment_link.link
    
    @http.route()
    def payment_pay(
        self, reference=None, amount=None, currency_id=None, partner_id=None, company_id=None,
        acquirer_id=None, access_token=None, invoice_id=None, **kwargs
    ):
        
        amount = self._cast_as_float(amount)
        if 'invoice_ids' in kwargs:
            invoice_ids = [int(x) for x in kwargs['invoice_ids'].split(',') if x.isdigit()]
            invoices_sudo = request.env['account.move'].sudo().browse(invoice_ids).exists()
            if not invoices_sudo:
                raise ValidationError(_("The provided parameters are invalid."))
            if len(invoices_sudo.mapped('commercial_partner_id')) > 1:
                raise ValidationError(_("Only pay invoices from the same customer."))
            if len(invoices_sudo.mapped('currency_id')) > 1:
                raise ValidationError(_("Only pay invoices from the same currency."))
            if len(invoices_sudo.mapped('company_id')) > 1:
                raise ValidationError(_("Only pay invoices from the same company."))
            first_invoice_sudo = invoices_sudo[0]
            # Check the access token against the invoice values. Done after fetching the invoice
            # as we need the invoice fields to check the access token.
            # if not payment_utils.check_access_token(
            #     access_token, first_invoice_sudo.partner_id.id, amount, first_invoice_sudo.currency_id.id
            # ):
            #     raise ValidationError(_("The provided parameters are invalid."))
            currency_id = first_invoice_sudo.currency_id.id
            partner_id = first_invoice_sudo.commercial_partner_id.id
            company_id = first_invoice_sudo.company_id.id

            kwargs.update({
                'invoice_ids': invoice_ids,
            })
        return super().payment_pay(
            reference=reference, amount=amount, currency_id=currency_id, partner_id=partner_id, company_id=company_id,
            acquirer_id=acquirer_id, access_token=access_token, invoice_id=invoice_id, **kwargs

        )

    def _get_custom_rendering_context_values(self, invoice_ids=None, **kwargs):
        """ Override of `payment` to add the invoice id in the custom rendering context values.

        :param int invoice_id: The invoice for which a payment id made, as an `account.move` id.
        :param dict kwargs: Optional data. This parameter is not used here.
        :return: The extended rendering context values.
        :rtype: dict
        """
        rendering_context_values = super()._get_custom_rendering_context_values(**kwargs)
        if invoice_ids:
            rendering_context_values['invoice_ids'] = invoice_ids

            # Interrupt the payment flow if the invoice has been canceled.
            # invoice_sudo = request.env['account.move'].sudo().browse(invoice_ids)
            #if invoice_sudo.state == 'cancel':
            #    rendering_context_values['amount'] = 0.0
        return rendering_context_values

    def _create_transaction(self, *args, invoice_ids=None, custom_create_values=None, **kwargs):
        """ Override of `payment` to add the invoice id in the custom create values.

        :param int invoice_id: The invoice for which a payment id made, as an `account.move` id.
        :param dict custom_create_values: Additional create values overwriting the default ones.
        :param dict kwargs: Optional data. This parameter is not used here.
        :return: The result of the parent method.
        :rtype: recordset of `payment.transaction`
        """
        ##import pdb; pdb.set_trace()
        if invoice_ids:
            if custom_create_values is None:
                custom_create_values = {}
            custom_create_values['invoice_ids'] = [Command.set(invoice_ids)]
        return super()._create_transaction(
            *args, custom_create_values=custom_create_values, **kwargs
        )
