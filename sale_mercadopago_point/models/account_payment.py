import hashlib
import logging
from datetime import datetime

import requests

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # MercadoPago Point fields
    mp_point_order_id = fields.Char(
        string='MercadoPago Order ID',
        help='Order ID returned by MercadoPago Point API',
        readonly=True
    )
    mp_point_order_status = fields.Char(
        string='MercadoPago Order Status',
        readonly=True
    )

    def _get_mp_point_idempotency_key(self):
        """Generate idempotency key from payment ID, partner ID and amount"""
        # Combine payment id, partner id and amount to create a unique hash
        key_string = f"{self.id}_{self.partner_id.id}_{self.amount}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _mp_point_api_request(self, endpoint, method='GET', data=None):
        """
        Abstract method to make API requests to MercadoPago Point
        :param endpoint: API endpoint (e.g., 'v1/orders', 'v1/orders/123')
        :param method: HTTP method ('GET', 'POST', 'PUT', 'DELETE')
        :param data: Request payload (for POST/PUT requests)
        :return: API response as dict
        """
        company = self.company_id
        if not company.mp_point_access_token:
            raise UserError(_('MercadoPago Access Token is not configured in company settings'))

        # Prepare headers
        headers = {
            'Authorization': f'Bearer {company.mp_point_access_token}',
            'Content-Type': 'application/json'
        }

        # Add idempotency key for POST requests
        if method.upper() == 'POST':
            headers['X-Idempotency-Key'] = self._get_mp_point_idempotency_key()

        # Build full URL
        base_url = company.get_mp_point_base_url()
        url = f"{base_url}/{endpoint.lstrip('/')}"

        try:
            # Make the request
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=30)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise UserError(_('Unsupported HTTP method: %s') % method)

            response.raise_for_status()
            result = response.json()

            return result

        except requests.RequestException as e:
            _logger.error(f"MercadoPago API request error: {str(e)}")
            raise UserError(_('MercadoPago API request error: %s') % str(e))
        except Exception as e:
            _logger.error(f"Unexpected error in MercadoPago API request: {str(e)}")
            raise UserError(_('Unexpected error in MercadoPago API request: %s') % str(e))

    def _get_mp_point_order_data(self):
        """Prepare order data for MercadoPago Point API"""
        # Get payment method line for MercadoPago Point configuration
        mp_point_method = self.env.ref('sale_mercadopago_point.account_payment_in_mercadopago_point', raise_if_not_found=False)
        payment_method_line = self.journal_id.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_method_id == mp_point_method
        )

        if not payment_method_line:
            raise UserError(_('MercadoPago Point payment method is not configured for this journal'))

        if not payment_method_line.mp_point_store_id or not payment_method_line.mp_point_pos_id:
            raise UserError(_('MercadoPago Point Store ID and POS ID must be configured in the payment method'))

        # Get base URL for webhook
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if not base_url:
            raise UserError(_('Base URL is not configured. Please set web.base.url system parameter.'))

        # Get payer information from partner
        partner = self.partner_id
        if not partner.l10n_latam_identification_type_id:
            raise UserError(_('Partner %s must have an identification type configured') % partner.name)

        if not partner.vat:
            raise UserError(_('Partner %s must have a VAT/Tax ID configured') % partner.name)

        identification_type = partner.l10n_latam_identification_type_id.name
        identification_number = partner.vat

        # Generate external reference with timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        external_reference = f"mercadopago_point_{self.id}_{timestamp}"

        return {
            "type": "payment",
            "payment_intent": "capture",
            "payment_mode": "in_person",
            "payer": {
                "identification": {
                    "type": identification_type,
                    "number": identification_number
                }
            },
            "order": {
                "type": "pos",
                "pos": {
                    "store_id": payment_method_line.mp_point_store_id,
                    "pos_id": payment_method_line.mp_point_pos_id
                }
            },
            "payment_method_options": {
                "pos": {
                    "amount": int(self.amount * 100),  # Convert to cents
                    "currency_id": self.currency_id.name
                }
            },
            "external_reference": external_reference,
            "notification_url": f"{base_url}/payment/mercadopago_point/webhook"
        }

    def _create_mp_point_order(self):
        """Create order in MercadoPago Point API"""
        data = self._get_mp_point_order_data()
        result = self._mp_point_api_request('v1/orders', method='POST', data=data)

        self.mp_point_order_id = result.get('id')
        self.mp_point_order_status = result.get('status')
        _logger.info(f"MercadoPago Point order created for payment {self.name}: {self.mp_point_order_id}")

        return result

    def _check_mp_point_order_status(self):
        """Check order status in MercadoPago Point API"""
        if not self.mp_point_order_id:
            return False

        endpoint = f'v1/orders/{self.mp_point_order_id}'
        result = self._mp_point_api_request(endpoint, method='GET')

        self.mp_point_order_status = result.get('status')

        return result

    def action_post(self):
        """Override action_post to handle MercadoPago Point payments"""
        mp_point_method = self.env.ref('sale_mercadopago_point.account_payment_in_mercadopago_point', raise_if_not_found=False)

        # Filter MercadoPago Point payments in draft state
        mp_point_payments = self.filtered(lambda p: p.payment_method_id == mp_point_method and p.state == 'draft')

        for payment in mp_point_payments:
            if not payment.mp_point_order_id:
                # Create new MercadoPago Point order
                payment._create_mp_point_order()
                # Keep payment in draft state until webhook confirmation
            else:
                # Check existing order status
                payment._check_mp_point_order_status()
                if payment.mp_point_order_status in ['cancelled', 'expired']:
                    payment.action_cancel()

        # Call super for non-MercadoPago payments or confirmed MercadoPago payments
        postable_payments = self - mp_point_payments.filtered(lambda p: p.mp_point_order_status != 'paid')
        return super(AccountPayment, postable_payments).action_post()

    def action_cancel(self):
        """Override action_cancel to handle MercadoPago Point order cancellation"""
        mp_point_method = self.env.ref('sale_mercadopago_point.account_payment_in_mercadopago_point', raise_if_not_found=False)

        for payment in self:
            if payment.payment_method_id == mp_point_method and payment.mp_point_order_id:
                # Here you could add logic to cancel the order in MercadoPago if needed
                payment.mp_point_order_status = 'cancelled'

        return super().action_cancel()

    def _process_mp_point_webhook(self, webhook_data):
        """Process MercadoPago Point webhook notification"""
        order_id = webhook_data.get('id')
        status = webhook_data.get('status')

        if order_id and str(order_id) == str(self.mp_point_order_id):
            self.mp_point_order_status = status

            if status == 'paid':
                # Payment confirmed, post the payment
                super(AccountPayment, self).action_post()
            elif status in ['cancelled', 'expired']:
                # Payment failed, cancel
                self.action_cancel()

            return True

        return False
