# Argentinean Payment Bundle

Groups multiple payments into a single "bundle receipt": a main payment (`is_main_payment=True`, amount=0) that concentrates the debt, withholdings, and write-off, plus linked payments (`link_payment_ids`) that represent the actual payment methods. Supports **multi-currency bundles** — linked payments can use journals in any currency (ARS, USD, EUR, etc.), and all amounts are expressed in the main payment's debt currency (B) via each linked payment's own `counterpart_rate`.

## Features

- **Payment bundles:** group multiple payments under a single main payment for unified receipt management.
- **Multi-currency linked payments:** a bundle can mix linked payments in ARS, USD, EUR, etc. Each linked payment computes its own `counterpart_rate` (A→B) according to its journal.
- **Withholding integration:** integrates with `l10n_ar_tax` to handle tax withholdings within the bundle.
- **Receipt books:** supports receipt book management via `account_payment_pro_receiptbook`.
- **Custom payment method:** adds `Payment multiple` for both inbound and outbound payments.

## Known issues / Roadmap

- Multiple receipt report not implemented for non-Argentine companies.
- Payment register wizard should not allow selecting the payment bundle journal.

## Dependencies

| Module | Purpose |
|--------|---------|
| `account_payment_pro` | Tri-currency payment model |
| `l10n_ar_tax` | Argentine withholdings |
| `account_payment_pro_receiptbook` | Receipt book management |

## Configuration

1. **Bundle journals:** journals with the `Payment multiple` method are auto-created for Argentine companies (post-init hook). Verify they are configured correctly.
2. **Receipt books:** configure as needed for payment receipt management.
3. **Withholding taxes:** set up in `l10n_ar_tax` to integrate with bundle payments.

## Usage

### Creating a bundle

1. Go to Payments, create a new payment selecting the `Payment multiple` method.
2. Add linked payments — each can use a different journal/currency.
3. The main payment concentrates debt selection, withholdings, and write-off.
4. Validation is done through the main payment.

### Multi-currency example

Invoice: 1.000 USD. Bundle with:
- Linked 1: 500 USD (cash, `counterpart_rate`=1.0) → 500 USD in B.
- Linked 2: 600.000 ARS (transfer, `counterpart_rate`≈0.000833) → 500 USD in B.
- IIBB withholding: 30 USD (≈36.000 ARS stored).

The system adjusts linked amounts automatically when withholdings change.

## Bug Tracker

Bugs are tracked on [GitHub Issues](https://github.com/ingadhoc/account-payment/issues).

## Credits

**Author:** ADHOC SA · [www.adhoc.com.ar](https://www.adhoc.com.ar)
**License:** AGPL-3.0 or later

---

See [DESIGN.md](DESIGN.md) for internal architecture and design decisions.
