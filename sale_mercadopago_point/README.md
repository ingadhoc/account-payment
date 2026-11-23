# Sale MercadoPago Point

This module integrates Odoo payment processing with MercadoPago Point API, allowing payments to be processed through MercadoPago Point terminals directly from Odoo payment forms.

## Features

- Integration with MercadoPago Point API
- Payment processing through account.payment forms
- Webhook support for payment confirmation
- Configurable MercadoPago credentials at company level
- Terminal and POS configuration at journal level
- Order status tracking and automatic payment posting

## Configuration

### Company Settings

1. Go to Settings > Companies > Edit your company
2. Navigate to the "MercadoPago Point" tab
3. Configure:
   - **Access Token**: Your MercadoPago access token
   - **Client ID**: Your MercadoPago client ID
   - **Client Secret**: Your MercadoPago client secret
   - **Sandbox Mode**: Enable for testing environment

### Journal Configuration

1. Go to Accounting > Configuration > Journals
2. Edit or create a payment journal
3. In the payment methods, add "MercadoPago Point"
4. Configure:
   - **Store ID**: MercadoPago Point Store ID
   - **POS ID**: MercadoPago Point POS ID

## Usage

1. Create a new payment (Accounting > Customers > Payments)
2. Select a journal configured with MercadoPago Point
3. Choose "MercadoPago Point" as payment method
4. Enter the payment amount
5. Optionally set an external reference
6. Click "Post" to create the MercadoPago Point order
7. The payment will remain in draft until confirmed by webhook
8. Once payment is confirmed, it will be automatically posted

## Webhook Configuration

The module provides a webhook endpoint at:
```
/payment/mercadopago_point/webhook
```

Configure this URL in your MercadoPago Point settings to receive payment notifications.

## Technical Details

### Models Extended

- **res.company**: Adds MercadoPago API configuration fields
- **account.journal**: Adds terminal configuration fields
- **account.payment**: Adds order tracking and payment processing logic

### API Integration

The module integrates with MercadoPago Point API endpoints:
- `POST /v1/orders`: Create payment orders
- `GET /v1/orders/{id}`: Check order status

### Payment Flow

1. User clicks "Post" on payment with MercadoPago Point method
2. Module creates order via MercadoPago API
3. Payment stays in draft state
4. MercadoPago sends webhook notification when payment is processed
5. Module receives webhook and updates payment status
6. If payment successful, automatically posts the payment
7. If payment failed, cancels the payment

## Requirements

- Odoo 18.0
- requests library
- Valid MercadoPago Point credentials

## License

AGPL-3.0
