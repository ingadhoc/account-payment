# Account Payment Multi

The **Account Payment Multi** module allows users to manage multiple invoice payments in Odoo. With this module, users can select multiple invoices and pay them with a single payment, streamlining the payment process for businesses.

## Features

- **Multi-Invoice Payment**: Select multiple invoices and process them as a single payment.
- **Batch Payment Reference**: Automatically generate a unique batch payment reference for grouped payments.
- **Portal Integration**: Enhanced portal views for selecting and paying invoices.
- **Frontend Enhancements**: Custom JavaScript for improved user interaction in the portal.

## Installation

1. Ensure the `account_payment` module is installed as it is a dependency.
2. Add this module to your Odoo addons path.
3. Update the module list and install the **Account Payment Multi** module.

## Configuration

- No additional configuration is required. The module integrates seamlessly with the existing payment and portal functionalities.

## Usage

1. Navigate to the **Customer Portal**.
2. Go to the **My Invoices** section.
3. Select multiple invoices using the checkboxes provided.
4. Click the **Pay Selected** button to proceed with the payment.
5. Review the payment summary and confirm the transaction.

## Technical Details

- **Controllers**: The module extends the payment portal controller to handle multi-invoice payments. See [`portal.py`](account_payment_multi/controllers/portal.py).
- **Models**: Adds a batch payment sequence to the company model for generating unique batch payment references. See [`company.py`](account_payment_multi/models/company.py).
- **Views**: Customizes portal templates for invoice selection and payment. See:
  - [`account_portal_templates.xml`](account_payment_multi/views/account_portal_templates.xml)
  - [`payment_form_template.xml`](account_payment_multi/views/payment_form_template.xml)
- **JavaScript**: Enhances the frontend with custom logic for selecting invoices and initiating payments. See [`payment_form.js`](account_payment_multi/static/src/js/payment_form.js).

## Dependencies

- `account_payment`

## Assets

The module includes the following assets:
- JavaScript: [`payment_form.js`](account_payment_multi/static/src/js/payment_form.js)

## License

This module is licensed under the LGPL-3 license.

## Author

- **Odoo, ADHOC SA**
- Website: [www.adhoc.com.ar](https://www.adhoc.com.ar)