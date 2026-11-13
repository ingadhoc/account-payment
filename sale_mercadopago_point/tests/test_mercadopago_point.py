from unittest.mock import patch, Mock
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestMercadoPagoPoint(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.user.company_id
        self.company.write({
            'mp_point_access_token': 'test_token',
            'mp_point_client_id': 'test_client',
            'mp_point_client_secret': 'test_secret',
            'mp_point_sandbox_mode': True,
        })

        self.journal = self.env['account.journal'].create({
            'name': 'MercadoPago Point Test',
            'type': 'bank',
            'code': 'MPP',
        })

        self.mp_method = self.env.ref('sale_mercadopago_point.account_payment_in_mercadopago_point')
        # Create payment method line with MercadoPago Point configuration
        self.method_line = self.env['account.payment.method.line'].create({
            'journal_id': self.journal.id,
            'payment_method_id': self.mp_method.id,
            'mp_point_store_id': 'test_store',
            'mp_point_pos_id': 'test_pos',
        })

        self.payment = self.env['account.payment'].create({
            'amount': 100.0,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'journal_id': self.journal.id,
            'payment_method_id': self.mp_method.id,
        })

    def test_mp_point_configuration(self):
        """Test MercadoPago Point configuration"""
        self.assertTrue(self.company.mp_point_access_token)
        self.assertTrue(self.method_line.mp_point_store_id)
        self.assertTrue(self.method_line.mp_point_pos_id)

    @patch('requests.post')
    def test_create_mp_point_order(self, mock_post):
        """Test creating MercadoPago Point order"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'id': 'test_order_id',
            'status': 'pending'
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.payment._create_mp_point_order()

        self.assertEqual(self.payment.mp_point_order_id, 'test_order_id')
        self.assertEqual(self.payment.mp_point_order_status, 'pending')
        self.assertEqual(result['id'], 'test_order_id')

    def test_missing_configuration(self):
        """Test error handling for missing configuration"""
        self.company.mp_point_access_token = False
        with self.assertRaises(UserError):
            self.payment._get_mp_point_headers()

        self.company.mp_point_access_token = 'test_token'
        self.journal.mp_point_store_id = False
        with self.assertRaises(UserError):
            self.payment._get_mp_point_order_data()

    def test_webhook_processing(self):
        """Test webhook processing"""
        self.payment.mp_point_order_id = 'test_order_id'

        # Test successful payment webhook
        webhook_data = {
            'id': 'test_order_id',
            'status': 'paid'
        }

        with patch.object(self.payment.__class__, 'action_post') as mock_post:
            result = self.payment._process_mp_point_webhook(webhook_data)
            self.assertTrue(result)
            self.assertEqual(self.payment.mp_point_order_status, 'paid')
            mock_post.assert_called_once()

        # Test failed payment webhook
        webhook_data = {
            'id': 'test_order_id',
            'status': 'cancelled'
        }

        with patch.object(self.payment.__class__, 'action_cancel') as mock_cancel:
            result = self.payment._process_mp_point_webhook(webhook_data)
            self.assertTrue(result)
            self.assertEqual(self.payment.mp_point_order_status, 'cancelled')
            mock_cancel.assert_called_once()

    @patch('requests.get')
    def test_check_order_status(self, mock_get):
        """Test checking order status"""
        self.payment.mp_point_order_id = 'test_order_id'

        mock_response = Mock()
        mock_response.json.return_value = {
            'id': 'test_order_id',
            'status': 'paid'
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.payment._check_mp_point_order_status()

        self.assertEqual(self.payment.mp_point_order_status, 'paid')
        self.assertEqual(result['id'], 'test_order_id')
