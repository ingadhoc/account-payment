# Argentinean Payment Bundle Early Discount

## Description

Technical bridge module between **Argentinean Payment bundle** and **Account Payment Early Discount**. On a payment bundle, the early payment discount is decided once, on the main payment, and the linked payments follow it.

It is installed automatically when both modules are installed.

## Main Features

### Date of the Discount
- **Main payment date**: the discount period is always checked with the date of the main payment.
- **Linked payments**: their dates do not change the discount. A linked payment dated after the discount period still gets the discount if the main payment is within it.
- **Date change**: changing the date of the main payment out of the discount period removes the discount, and the linked payments go back to the full debt.

### Main Payment
- **Single decision**: the **Exclude** and **Recalculate** buttons are only on the main payment. The linked payments do not show the discount and cannot turn it on or off.
- **Amount**: the amount of the main payment stays zero, as in any bundle. The discount does not change it.
- **Difference**: while the bundle is built, the difference of the main payment already has the discount it gets if the linked payments pay all the selected debt.
- **Early Payment Discount**: the label and the buttons are always shown. The amount is shown only once the linked payments pay a discounted invoice, and it is the discount applied if the bundle is posted now. With several invoices, only the ones already paid count.
- **Credit notes**: posting the bundle creates the credit notes once, from the main payment. They belong to the main payment.
- **Returned check**: if a check of a linked payment is returned to the customer, the main payment shows the warning with its credit notes.

### Linked Payments
- **Suggested amount**: the difference of a linked payment already has the discount of the main payment, so **→ Amount** suggests the amount with discount.
- **Excluded discount**: with the discount excluded on the main payment, the linked payments suggest the full debt and no credit note is created.

## Usage

1. Create and post customer invoices with a payment term with early discount.
2. Register a payment from the invoices and select the **Multiple payments** journal. The date of this main payment is the one that decides the discount.
3. Add the linked payments. **→ Amount** suggests what is left to pay with discount.
4. Optionally, use **Exclude** on the main payment when the customer does not take the discount.
5. Post the main payment. The credit notes are created and the invoices get paid.

## Limitations

- The amount of a linked payment is not changed when the discount is excluded or recalculated on the main payment once the linked payment has an amount. If the customer already paid the full debt and the discount is recalculated, the credit note is created anyway and the customer gets a credit.
