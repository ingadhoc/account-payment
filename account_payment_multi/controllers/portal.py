from odoo import _, fields, http, Command
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request, route

from odoo.addons.payment.controllers import portal as payment_portal


class PaymentPortal(payment_portal.PaymentPortal):

    def _get_selected_invoices_domain(self, due_date, partner_id=None):
        return [
            ('state', 'not in', ('cancel', 'draft')),
            ('move_type', 'in', ('out_invoice', 'out_receipt')),
            ('payment_state', 'not in', ('in_payment', 'paid')),
            ('partner_id', '=', partner_id or request.env.user.partner_id.id),
            ('invoice_date_due', '<=', due_date)
        ]

    @http.route(['/my/invoices/selected'], type='http', auth='public', methods=['GET'], website=True, sitemap=False)
    def portal_my_selected_invoices(self, **kw):
        try:
            request.env['account.move'].check_access_rights('read')
        except (AccessError, MissingError):
            return request.redirect('/my')

        invoice_id = int(kw.get('invoice_id'))
        due_date = request.env['account.move'].browse(invoice_id).invoice_date_due
        selected_invoices = request.env['account.move'].search(self._get_selected_invoices_domain(due_date=due_date))
        values = self._selected_invoices_get_page_view_values(selected_invoices, **kw)
        return request.render("account_payment_multi.portal_selected_invoices_page", values) \
            if 'payment' in values else request.redirect('/my/invoices/selected')

    def _selected_invoices_get_page_view_values(self, selected_invoices, **kwargs):
        values = {'page_name': 'selected_invoices'}

        if len(selected_invoices) == 0:
            return values

        first_invoice = selected_invoices[0]
        partner = first_invoice.partner_id
        company = first_invoice.company_id
        currency = first_invoice.currency_id

        if any(invoice.partner_id != partner for invoice in selected_invoices):
            raise ValidationError(_("Selected invoices should share the same partner."))
        if any(invoice.company_id != company for invoice in selected_invoices):
            raise ValidationError(_("Selected invoices should share the same company."))
        if any(invoice.currency_id != currency for invoice in selected_invoices):
            raise ValidationError(_("Selected invoices should share the same currency."))

        total_amount = sum(selected_invoices.mapped('amount_total'))
        amount_residual = sum(selected_invoices.mapped('amount_residual'))
        batch_name = company.get_next_batch_payment_communication() if len(selected_invoices) > 1 \
            else first_invoice.name

        values['payment'] = {
            'date': fields.Date.today(),
            'reference': batch_name,
            'amount': total_amount,
            'currency': currency,
        }

        common_view_values = self._get_common_page_view_values(
            invoices_data={
                'partner': partner,
                'company': company,
                'total_amount': total_amount,
                'currency': currency,
                'amount_residual': amount_residual,
                'payment_reference': batch_name,
            },
            multi=True,
            **kwargs)

        values |= common_view_values
        return values

    def _get_common_page_view_values(self, invoices_data, access_token=None, **kwargs):
        logged_in = not request.env.user._is_public()
        # We set partner_id to the partner id of the current user if logged in, otherwise we set it
        # to the invoice partner id. We do this to ensure that payment tokens are assigned to the
        # correct partner and to avoid linking tokens to the public user.
        partner_sudo = request.env.user.partner_id if logged_in else invoices_data['partner']
        invoice_company = invoices_data['company'] or request.env.company

        availability_report = {}
        # Select all the payment methods and tokens that match the payment context.
        providers_sudo = request.env['payment.provider'].sudo()._get_compatible_providers(
            invoice_company.id,
            partner_sudo.id,
            invoices_data['total_amount'],
            currency_id=invoices_data['currency'].id,
            report=availability_report,
        )  # In sudo mode to read the fields of providers and partner (if logged out).
        payment_methods_sudo = request.env['payment.method'].sudo()._get_compatible_payment_methods(
            providers_sudo.ids,
            partner_sudo.id,
            currency_id=invoices_data['currency'].id,
            report=availability_report,
        )  # In sudo mode to read the fields of providers.
        tokens_sudo = request.env['payment.token'].sudo()._get_available_tokens(
            providers_sudo.ids, partner_sudo.id
        )  # In sudo mode to read the partner's tokens (if logged out) and provider fields.

        # Make sure that the partner's company matches the invoice's company.
        company_mismatch = not PaymentPortal._can_partner_pay_in_company(
            partner_sudo, invoice_company
        )

        portal_page_values = {
            'company_mismatch': company_mismatch,
            'expected_company': invoice_company,
        }
        payment_form_values = {
            'show_tokenize_input_mapping': PaymentPortal._compute_show_tokenize_input_mapping(
                providers_sudo
            ),
        }
        payment_context = {
            'amount': invoices_data['amount_residual'],
            'currency': invoices_data['currency'],
            'partner_id': partner_sudo.id,
            'providers_sudo': providers_sudo,
            'payment_methods_sudo': payment_methods_sudo,
            'tokens_sudo': tokens_sudo,
            'availability_report': availability_report,
            'access_token': access_token,
            'payment_reference': invoices_data.get('payment_reference', False),
            'landing_route': '/my/invoices/',
        }
        # Merge the dictionaries while allowing the redefinition of keys.
        values = portal_page_values | payment_form_values | payment_context | self._get_extra_payment_form_values(**kwargs)

        return values

    def _get_extra_payment_form_values(self, invoice_id=None, access_token=None, **kwargs):
        form_values = super()._get_extra_payment_form_values(invoice_id=None, access_token=None, **kwargs)
        if kwargs.get('multi'):
            form_values.update({
                'transaction_route': f'/invoice/transaction/selected/{invoice_id}',
            })

        return form_values

    @route('/invoice/transaction/selected/<int:invoice_id>', type='json', auth='public')
    def selected_invoices_transaction(self, payment_reference, **kwargs):
        """ Create a draft transaction for selected invoices and return its processing values.

        :param str payment_reference: The reference to the current payment
        :param dict kwargs: Locally unused data passed to `_create_transaction`
        :return: The mandatory values for the processing of the transaction
        :rtype: dict
        :raise: ValidationError if the user is not logged in, or all the selected invoices don't share the same currency.
        """

        logged_in = not request.env.user._is_public()
        if not logged_in:
            raise ValidationError(_("Please log in to pay your selected invoices"))
        partner = request.env.user.partner_id

        invoice_id = int(kwargs.get('invoice_id'))
        due_date = request.env['account.move'].browse(invoice_id).invoice_date_due

        selected_invoices = request.env['account.move'].search(self._get_selected_invoices_domain(due_date))
        currencies = selected_invoices.mapped('currency_id')
        if not all(currency == currencies[0] for currency in currencies):
            raise ValidationError(_("Impossible to pay all the selected invoices if they don't share the same currency."))
        self._validate_transaction_kwargs(kwargs, ('invoice_id',))
        return self._process_transaction(partner.id, currencies[0].id, selected_invoices.ids, payment_reference, **kwargs)

    def _process_transaction(self, partner_id, currency_id, invoice_ids, payment_reference, **kwargs):
        kwargs.update({
            'currency_id': currency_id,
            'partner_id': partner_id,
        })  # Inject the create values taken from the invoice into the kwargs.

        tx_sudo = self._create_transaction(
            custom_create_values={
                'invoice_ids': [Command.set(invoice_ids)],
                'reference': payment_reference,
            },
            **kwargs,
        )
        return tx_sudo._get_processing_values()
