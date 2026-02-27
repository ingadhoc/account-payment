# Account Cashbox Bundle

Technical bridge module that ensures proper integration between Account Cashbox and Payment Bundle functionality.

## Features

This module provides seamless integration between cashbox operations and payment bundles:

- **Excludes bundle journals from cashbox configuration**: Payment bundle journals are automatically filtered out from cashbox journal selection, as they operate differently from regular cashbox transactions.

- **Smart cashbox session handling**: Main bundle payments automatically bypass cashbox session requirements, while child payments within the bundle maintain proper cashbox controls.

- **Domain restrictions**: Prevents configuration errors by ensuring bundle payment methods cannot be associated with cashbox sessions.

## Installation

This module is set to `auto_install`, meaning it will be automatically installed when both dependencies are present:

- `account_cashbox`
- `l10n_ar_payment_bundle`

No manual installation is required.

## Configuration

No configuration needed. The module works automatically once installed.

## Usage

### Cashbox Configuration

When setting up a cashbox:

1. Navigate to **Accounting → Configuration → Cashboxes**
2. Create or edit a cashbox
3. When selecting journals, payment bundle journals will be automatically excluded from available options

This ensures only regular cash and bank journals can be associated with cashbox sessions.

### Payment Operations

**Bundle Payments (Main):**
- When creating a payment using a payment bundle journal, the cashbox session requirement is automatically bypassed
- This is correct behavior as bundle payments are container/parent payments

**Child Payments:**
- Individual payments within a bundle will follow standard cashbox rules
- Cashbox session requirements are determined by user configuration and journal settings

## Technical Details

### Models Extended

**account.cashbox**
- Adds domain restriction to `journal_ids` field to exclude journals with payment_bundle methods

**account.payment**
- Overrides `_compute_requiere_account_cashbox_session()` to disable cashbox requirement for main payments

### Dependencies

- `account_cashbox`
- `l10n_ar_payment_bundle`

## Bug Tracker

Bugs are tracked on [GitHub Issues](https://github.com/adhoc-ar/account-payment/issues).

If you encounter any issues, please check if it has already been reported. If not, please [create a new issue](https://github.com/adhoc-ar/account-payment/issues/new) with detailed steps to reproduce.

## Credits

### Authors

- ADHOC SA

### Contributors

- ADHOC SA

### Maintainer

This module is maintained by **ADHOC SA**.

For more information, please visit <https://www.adhoc.com.ar>
