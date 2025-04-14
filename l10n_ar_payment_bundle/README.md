# Argentinean Payment Bundle

The **Argentinean Payment Bundle** module enhances Odoo's payment functionality by introducing features tailored to the Argentinean market. It allows for the management of complex payment scenarios, including payment bundles, linked payments, and withholding taxes.

## Features

- **Payment Bundles**: Group multiple payments into a single main payment for easier management.
- **Linked Payments**: Automatically create and manage linked payments associated with a main payment.
- **Withholding Tax Management**: Integrates with the `l10n_ar_tax` module to handle withholding taxes during payment processing.
- **Receipt Books**: Supports receipt book management for payments, leveraging the `account_payment_pro_receiptbook` module.
- **Custom Payment Methods**: Adds a new payment method, `Payment multiple`, for both inbound and outbound payments.

## Known issues / Roadmap
 - ** Multiple receipt report not implemented in non Argentina companies
 - ** Payment regiter wizard should not allow to select payment bundle journal

## Installation

To install this module, ensure the following dependencies are installed:

- `account_payment_pro`
- `l10n_ar_tax`
- `account_payment_pro_receiptbook`

Once the dependencies are installed, add this module to your Odoo instance and install it through the Apps menu.

## Configuration

1. **Payment Bundle Journals**:
   - Ensure that journals using the `Payment multiple` method are configured correctly.
   - Journals with this payment method cannot have a currency assigned.

2. **Receipt Books**:
   - Configure receipt books for managing payments if required.

3. **Withholding Taxes**:
   - Set up withholding taxes in the `l10n_ar_tax` module to integrate with payments.

## Usage

### Creating a Payment Bundle
1. Navigate to the **Payments** menu.
2. Create a new payment and select the `Payment multiple` method.
3. Add linked payments to the main payment as needed.

### Managing Linked Payments
- Linked payments are automatically created and managed under the main payment.
- Validation of linked payments must be done through the main payment to ensure consistency.

### Withholding Taxes
- Withholding taxes are automatically calculated and applied during payment processing if configured.

### Receipt Books
- Use receipt books to manage payment receipts if enabled.

## Technical Details

- **Post-Initialization Hook**: The module includes a post-init hook to create journals for companies using the Argentinean Chart of Accounts.
- **Custom Payment Method**: The `Payment multiple` method is defined in the `data/account_payment_method_data.xml` file.
- **Views**: Customizations to the payment form and tree views are defined in `views/account_payment_view.xml`.

## Credits

- **Author**: ADHOC SA
- **Website**: [www.adhoc.com.ar](https://www.adhoc.com.ar)
- **License**: AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

## Bug Tracker

Bugs are tracked on [GitHub Issues](https://github.com/ingadhoc/account-payment/issues). If you encounter an issue, please report it with detailed feedback.

## Maintainer

This module is maintained by **ADHOC SA**. For contributions or inquiries, visit [www.adhoc.com.ar](https://www.adhoc.com.ar).
