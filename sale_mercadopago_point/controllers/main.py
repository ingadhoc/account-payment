import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MercadoPagoPointController(http.Controller):

    @http.route('/payment/mercadopago_point/webhook', type='json', auth='none', methods=['POST'], csrf=False)
    def mercadopago_point_webhook(self):
        """Handle MercadoPago Point webhook notifications"""
        try:
            data = request.jsonrequest

            # Extract relevant information from webhook
            order_id = data.get('id')
            status = data.get('status')

            if not order_id:
                _logger.warning("MercadoPago Point webhook without order ID")
                return {'status': 'error', 'message': 'Missing order ID'}

            # Find the payment with this order ID
            payment = request.env['account.payment'].sudo().search([
                ('mp_point_order_id', '=', order_id)
            ], limit=1)

            if not payment:
                _logger.warning(f"No payment found for MercadoPago Point order ID: {order_id}")
                return {'status': 'error', 'message': 'Payment not found'}

            # Process the webhook
            result = payment._process_mp_point_webhook(data)

            if result:
                _logger.info(f"Payment {payment.name} confirmed via MercadoPago Point webhook (status: {status})")
                return {'status': 'success'}
            else:
                _logger.error(f"Failed to process MercadoPago Point webhook for payment {payment.name}")
                return {'status': 'error', 'message': 'Failed to process webhook'}

        except Exception as e:
            _logger.error(f"Error processing MercadoPago Point webhook: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    @http.route('/payment/mercadopago_point/status/<int:payment_id>', type='json', auth='user', methods=['GET'])
    def check_payment_status(self, payment_id):
        """Manual endpoint to check payment status"""
        try:
            payment = request.env['account.payment'].browse(payment_id)
            if not payment.exists():
                return {'status': 'error', 'message': 'Payment not found'}

            if payment.mp_point_order_id:
                order_data = payment._check_mp_point_order_status()
                return {
                    'status': 'success',
                    'order_status': payment.mp_point_order_status,
                    'order_data': order_data
                }
            else:
                return {'status': 'error', 'message': 'No MercadoPago Point order ID'}

        except Exception as e:
            _logger.error(f"Error checking MercadoPago Point payment status: {str(e)}")
            return {'status': 'error', 'message': str(e)}
