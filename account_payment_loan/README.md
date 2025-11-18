# Account Payment Personal Loan

## Description

This module extends Odoo's accounting functionality to manage personal loans to customers. It allows you to register loans, calculate late payment interest, manage installments, and track customer debt.

## Main Features

### Loan Management
- **Loan Registration**: Register new loans to customers with or without refinancing existing debts.
- **Installment Plans**: Configuration of payment plans with customizable monthly installments.
- **Credit/Loan Cards**: Define specific cards for loans with configurable due date methods.

### Interest Calculation
- **Late Payment Interest**: Automatic calculation of interest on overdue payments.
- **Daily Interest**: Calculates daily interest based on the monthly interest configured in the company.
- **Financial Surcharges**: Integration with financial surcharges in payments.

### Due Date Methods
The module offers two methods for calculating due dates:
- **Same day of creation**: Installments are due each month on the same day the loan was created.
- **Same day number**: Installments are due each month on the same day number.

### Reports and Tracking
- **Loan Debt Report**: Detailed view of each customer's outstanding debt.
- **Promissory Note**: Generation of promissory notes for registered loans.
- **Extra Charges**: Ability to add additional charges to loans.

## Configuration

### 1. Company Configuration

Go to **Accounting > Configuration > Settings** and configure:

- **Loan Journal**: Select the accounting journal to register loans.
- **Loan Account**: The default account for loans.
- **Late Payment Interest**: Monthly interest percentage applied to overdue payments.

### 2. Loan Card Configuration

Go to **Accounting > Configuration > Cards** and:

1. Create or edit a card.
2. Check the **Is Loan** option.
3. Configure the **Due Method**:
   - **every month on the same day it was created**: Maintains the same day of the creation month.
   - **every month on the same day number**: Uses the same day number each month.
4. Specify the **Due Day** if necessary.

### 3. Installment Plans

Configure the installment plans available for loans in **Accounting > Configuration > Installment Plans**.

## Usage

### Register a New Loan

1. Go to **Accounting > Customers > Payments** or from the customer contact view.
2. Select the invoices or journal items to include in the loan.
3. Click on **Action > Register Loan**.
4. In the wizard:
   - Select the loan **Card**.
   - Choose the **Installment Plan**.
   - Indicate if it is **Invoiceable** (will create a Debit Note) or not (will create a journal entry).
   - Add an internal note if necessary.
5. Click on **Register Loan**.

### Make a Loan Payment

1. Go to **Accounting > Customers > Payments**.
2. Create a new payment.
3. Select the loan lines to pay.
4. The system will automatically calculate **Late Payment Surcharges** if there are overdue payments.
5. Confirm the payment.

### View Debt Report

1. Go to **Accounting > Reports > Loan Debt** (or from the customer contact).
2. Select the customer or leave blank to see all.
3. The report will show:
   - Loans granted
   - Overdue and pending installments
   - Accumulated interest
   - Outstanding balance

### Add Extra Charges

1. From an existing loan, use **Action > Extra Charges**.
2. Specify the amount and concept of the charge.
3. Confirm to add the charge to the loan.

## Dependencies

This module requires the following modules:

- `card_installment`: Management of cards and installment plans.
- `account_debit_note`: Creation of debit notes.
- `account_payment_financial_surcharge`: Management of financial surcharges.

## Permissions

The module includes the following security groups:

- **Loan User**: Can view and manage loans.
- **Loan Manager**: Full access to loan configuration and management.

## Main Models

- `account.card`: Loan cards with due date configuration.
- `account.card.installment`: Installment plans.
- `account.payment`: Payments with late payment interest calculation.
- `account.move`: Loan journal entries with installment tracking.
- `account.loan.register`: Wizard for registering new loans.
- `account.loan.debt.report`: Loan debt report.
- `account.loan.extra.charges`: Wizard to add extra charges.

## Technical Notes

- Interest calculation is performed automatically when creating a payment.
- Loans can be refinanced including existing debt.
- The module uses the `post_init_hook` for initialization.
- Compatible with Odoo 19.0.

## Author

**ADHOC SA**
- Website: www.adhoc.com.ar
- License: AGPL-3

## Support

To report issues or request new features, contact ADHOC SA.
