# Account Payment Pro Breakdown

## Description

Lets the user decide how much of a payment goes to each selected debt, when the payment settles only part of them. Without it, Odoo spreads the payment by due date and the user cannot choose.

Payments that do not use the breakdown behave as before.

## Main Features

### Breakdown Wizard
- **Break Down Amount**: on a draft payment with selected debts, the button next to **Remove All** opens a wizard with one line per debt, by due date, with its amount due and the amount to allocate.
- **Fixed amount**: the payment amount is not edited nor recalculated: it is only broken down. The amounts must add up to it, and a debt cannot receive more than it owes.
- **Currency**: the amounts are in the currency of the debts, the same one the debts show.

### Breakdown Tab
- **Breakdown**: once saved, a tab next to **Debts** shows each debt with its amount. In draft the amounts can be edited and the lines deleted; deleting all of them leaves the payment as before. When the amounts do not add up to the payment, the tab shows the difference.
- **Posted payments**: the tab is hidden; the **Paid** tab already shows how much each debt received.

### Journal Entry
- **One counterpart line per debt**: the counterpart of the entry is split by the breakdown. The liquidity lines do not change, so a payment with several checks works the same.
- **Reconciliation**: on posting, each part is reconciled with its own debt and what was not allocated stays open. Debts in another currency keep the rate of the payment for each part, and the exchange difference is booked per debt.
- **Back to draft**: the entry follows the breakdown again on the next posting, and editing the payment in draft keeps the parts while they still add up.

### Posting Checks
A payment with a breakdown cannot be posted when the amounts do not add up to the payment, a debt of the breakdown is no longer selected, a debt receives more than it owes now, or the payment has a write-off or withholdings.

## Known Limits

- **Write-off and withholdings**: a payment with any of them cannot be broken down yet.
- **Payment bundle**: not supported.

## Usage

1. Create a customer receipt or a supplier payment and select the debts.
2. Click **Break Down Amount**, set the amount for each debt and confirm.
3. Check the **Breakdown** tab and post the payment.
