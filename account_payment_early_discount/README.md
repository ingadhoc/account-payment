# Account Payment Early Discount

## Description

Applies the early payment discount of the payment terms on customer invoices paid with Payment Pro. When the payments that complete the invoice are all done within the discount period, a credit note for the discount is created, posted and reconciled with the invoice and the payment.

Companies without Payment Pro (`use_payment_pro` disabled) keep the native Odoo early payment discount.

## Main Features

### Credit Note
- **Automatic**: the credit note is created when the payment that completes the invoice is posted. There is no manual button.
- **Partial payments**: several payments are accepted, as long as all of them are done within the discount period. Regular credit notes are not payments: they do not have to be within the period.
- **Taxes**: one discount line per set of taxes of the invoice lines, so VAT and perceptions are refunded in the same proportion. Price-included taxes are respected. Every tax charged on the invoice is refunded, even when the credit note does not reach a minimum of the whole document, such as the minimum base of a perception.
- **Link to the invoice**: the credit note is created with the credit note wizard, so it is linked to the invoice and gets the document type of the localization.
- **Date**: the credit note is dated on the day the payment is posted. The payment date is only used to check the discount period.

### Several Invoices
The payment is spread over the selected debt in the same order Odoo reconciles it: first the invoice due first and, with the same due date, the smaller amount. Every invoice with a valid discount that gets fully paid with its share receives its credit note.

### Draft Payment
- **Suggested amount**: new payments suggest the amount with discount instead of the full debt, when opened from the invoice, when debt is added and when the payment date changes. An amount set by the user is kept.
- **Early Payment Discount**: next to the payment total, the discount to apply and the difference after the discount.
- **Write-off warning**: if the payment has a write-off and, with the discount, the payment exceeds the debt, a warning is shown. It does not block the payment.
- **Debt lines**: the **Discount Until** and **Amount with Discount** columns are shown only on the invoices that get the discount if paid today.

## Configuration

1. Go to **Accounting > Configuration > Settings** and, under **Early payment discounts**, set the **Early Discount Loss** account. The credit note lines use it.
2. Go to **Accounting > Configuration > Payment Terms** and, on a payment term with a single line at 100%, enable **Early Discount** and set the percentage and the number of days.

Only the **Included** tax computation (percentage over the invoice total) is supported.

## Usage

1. Create and post a customer invoice with the payment term.
2. Register a payment within the discount period. The suggested amount already has the discount.
3. Post the payment. The credit note is created, posted and reconciled, and the invoice gets paid.

## Customization

The credit note flow is split in methods of `account.move` that can be overridden:

- `_prepare_early_discount_reversal_vals`: values of the credit note wizard (journal, date, reason).
- `_prepare_early_discount_line_vals`: discount lines of the credit note.
- `_fix_early_discount_tax_amounts`: fixes the tax amounts of the credit note lines, so the taxes charged on the invoice are refunded.
- `_create_early_discount_credit_note`: creates the credit note in draft.
- `_post_early_discount_credit_note`: posts the credit note. Override it to leave the credit note in draft for review: the payment is posted anyway and the credit note is not reconciled.

## Limitations

- Only customer invoices.
- Only payment terms with a single line and the **Included** computation.
- Invoices in a foreign currency: the credit note is in the invoice currency, and the suggested amount converts the discount with the rate Payment Pro uses for the debt, the one of the invoice. If the rate of the payment date is different, the suggested amount does not complete the discounted amount and has to be adjusted by hand.
