# Account Payment Personal Loan

## Description

This module extends Odoo's accounting functionality to manage personal loans to customers. It allows you to register loans, calculate late payment interest, manage installments, and track customer debt.

## Main Features

### Loan Management
- **Loan Registration**: Turn the pending balance of a customer invoice or credit note into a loan paid in monthly installments.
- **Refinancing**: Refinance existing loans, including their overdue interest, into a new loan.
- **Installment Plans**: Loans use the installment plans of the cards, with their surcharge coefficient and number of installments.
- **Loan Cards**: Define specific cards for loans with configurable due date methods.
- **Readable Entries**: The loan entry reference names its origin ("Loan of ...", "Refinancing of ...") and each installment line is labeled "<origin> | Installment N".

### Interest Calculation
- **Late Payment Interest**: Interest on overdue installments is calculated on draft payments and posted as a separate entry when the payment is confirmed.
- **Daily Interest**: The monthly rate configured in the company is prorated to a daily rate (1/30 of the monthly rate) and applied to the residual of each overdue installment.
- **Financial Surcharge**: The surcharge of the installment plan can be invoiced (debit note, or a new line on a draft invoice) or recorded in the loan entry.

### Due Date Methods
The module offers two methods for calculating due dates:
- **Same day of creation**: Installments are due each month on the same day the loan was created.
- **Same day number**: Installments are due each month on the configured day number (or the last day of the month, if shorter).

### Reports and Tracking
- **Loan Debt Report**: Customer's pending loan installments, overdue interest and amount to pay.
- **Promissory Note**: PDF promissory note for loan entries, with the invoiced products and the installments.
- **Extra Charges**: Ability to add additional charges to loans.
- **Terms & Conditions**: Default loan terms added to the loan description.

### Branches
- Branches use the loan settings (journal, interest rate and accounts) of their parent company, unless they set their own.

## Configuration

### 1. Company Configuration

On installation, and when a chart of accounts is loaded, the module creates the "Personal Loans" journal (code LOA) and the accounts "Account Receivable Loan", "Account Interest Loan" and "Account Extra Charges Loan", and sets them in the company.

Go to **Accounting > Configuration > Settings**, section **Loan Settings** (under Default Accounts), to review them:

- **Default Loan Journal**: Journal to register loans. Its default account is the loan receivable account.
- **Late Payment Interest**: Monthly interest percentage applied to overdue installments.
- **Account for Late Payment Interest**: Income account for late payment interest and for the non invoiced financial surcharge.
- **Account for Loan Extra Charges**: Income account for loan extra charges.
- **Default Loan Terms & Conditions**: Text added to the description of every new loan.

### 2. Loan Card Configuration

Go to **Accounting > Configuration > Cards** and:

1. Create or edit a card.
2. Check the **Is Loan** option.
3. Configure the **Loan Due Method**:
   - **every month on the same day it was created**: Maintains the same day of the creation month.
   - **every month on the same day number**: Uses the same day number each month.
4. Specify the **Due Day** (required with the "same day number" method).

### 3. Installment Plans

Configure the installment plans of the loan card in the card itself, or in **Accounting > Configuration > Installments**.

## Usage

### Register a New Loan

1. Go to **Accounting > Customers > Invoices** and open a customer invoice or credit note with a pending balance (draft or posted).
2. Click on the **Register Loan** button in the header.
3. In the wizard:
   - Select the **Loan** card.
   - Choose the **Installment Plan** and check the **Amount** to finance.
   - Indicate if it is **Invoiceable**: the surcharge is invoiced with a Debit Note (posted invoice) or a new line (draft invoice). If not, the surcharge is recorded in the loan entry.
   - Add an internal note if necessary.
4. Click on **Register Loan**. The loan entry is posted and reconciled with the invoice, and a message with the loan is posted on the invoice.

### Make a Loan Payment

1. Go to **Accounting > Customers > Payments**.
2. Create a new payment.
3. Select the loan lines to pay.
4. The system will automatically calculate the **Loan Surcharge** if there are overdue installments.
5. Confirm the payment. The late payment interest entry is posted and added to the paid lines.

### View Debt Report

1. Go to **Accounting > Customers > Customers Ledger** (journal items grouped by customer).
2. On the customer's group row, click the **Loan** button.
3. The report shows the customer's pending loan installments, the **Financial Surcharge** for overdue installments and the **Amount to Pay**. Optionally filter by loan.
4. From there you can **Pay selected lines**, **refinance loans** or post the overdue interest with **Debt**.

### Add Extra Charges

1. Go to **Accounting > Customers > Customers Ledger**.
2. On the customer's group row, click the **Loan Extra Charges** button.
3. Select the loan, and enter the label and the amount of the charge.
4. Click on **Add**.

### Print the Promissory Note

1. Open a loan entry.
2. Go to **Print > PDF Promissory Note**.

## Dependencies

This module requires the following modules:

- `card_installment`: Management of cards and installment plans.
- `account_debit_note`: Creation of debit notes.
- `account_payment_financial_surcharge`: Management of financial surcharges.

## Permissions

- The loan wizards are available to the **Invoicing** group (`account.group_account_invoice`).
- **Loan administration**: Can see the last interest calculation date of loan entries.

## Main Models

- `account.card`: Loan cards with due date configuration.
- `account.card.installment`: Installment plans.
- `account.payment`: Payments with late payment interest calculation.
- `account.move`: Loan journal entries with installment tracking.
- `res.company` / `res.config.settings`: Loan settings.
- `account.loan.register`: Wizard for registering and refinancing loans.
- `account.loan.debt.report`: Loan debt report.
- `account.loan.extra.charges`: Wizard to add extra charges.

## Technical Notes

- Interest calculation is performed automatically on draft payments.
- Loans can be refinanced including existing debt.
- The module uses the `post_init_hook` for initialization.
- Compatible with Odoo 20.0.

## Author

**ADHOC SA**
- Website: www.adhoc.com.ar
- License: AGPL-3

## Support

To report issues or request new features, contact ADHOC SA.
