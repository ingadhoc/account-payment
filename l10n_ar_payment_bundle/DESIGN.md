# DESIGN — l10n_ar_payment_bundle

Internal architecture reference for developers maintaining or extending the module.

---

## Architecture overview

A bundle payment consists of:

- **Main payment** (`is_main_payment=True`): amount=0, holds the debt selection, withholdings, and write-off. Uses the `Payment multiple` journal.
- **Linked payments** (`link_payment_ids`): real payment methods (cash, transfer, check, etc.). Each can use a different journal/currency.

The main payment defines the cancellation currency (B) via `counterpart_currency_id` / `destination_currency_id`. All linked payments inherit B from the main and their `counterpart_rate` (A→B) is computed independently based on their own journal currency.

---

## Currency model

Same tri-currency model as `account_payment_pro`:

| Symbol | Field | In the bundle |
|--------|-------|--------------|
| **A** | `currency_id` | Journal currency of each payment. Can differ between main and linked. |
| **B** | `destination_currency_id` | Cancellation currency. Defined by main, inherited by all linked. |
| **C** | `company_currency_id` | ARS. Same for all. |

Each linked payment has its own:
- `counterpart_rate` = `_get_conversion_rate(A_linked, B)`
- `accounting_rate` = `_get_conversion_rate(C, A_linked)`
- `counterpart_currency_amount` = `amount × counterpart_rate` (linked's contribution in B)

---

## Key methods

### `_compute_counterpart_currency_amount` (main payment override)

The main payment has `amount=0`. Its `counterpart_currency_amount` represents what it cancels via withholdings + write-off:

```python
rec.counterpart_currency_amount = rec.withholdings_amount + rec.write_off_amount
```

Both `withholdings_amount` and `write_off_amount` are already in B after the `account_payment_pro` refactor — no conversion needed.

### `_compute_payment_difference` (linked payments)

Operates entirely in currency B:

```python
total_payments_in_b = sum(main.link_payment_ids.mapped("counterpart_currency_amount"))
payment_difference = main.selected_debt - total_payments_in_b - main.withholdings_amount - main.write_off_amount
```

This works for any mix of linked currencies because each linked's `counterpart_currency_amount` is already in B.

### `_onchange_withholdings` (linked payments)

When withholdings change, linked payment amounts are adjusted. Since `payment_difference` is in B and `amount` is in A, the conversion B→A is needed:

```python
diff_in_a = rec.payment_difference / rec.counterpart_rate
rec.amount += diff_in_a
```

### `bundle_counterpart_currency_amount`

Sum of all linked payments' `counterpart_currency_amount`. Currency field: `destination_currency_id` (B).

### `_compute_available_journal_ids`

Linked payments can use **any** journal (including foreign-currency journals). Only the bundle journal itself is excluded.

---

## Design decisions

### Any journal allowed for linked payments

The old restriction `not j.currency_id` prevented foreign-currency linked payments. Removed to enable multi-currency bundles. Each linked computes its own `counterpart_rate` from its journal currency to B.

### `counterpart_rate` is NOT propagated as default

When creating linked payments, `counterpart_currency_id` (B) is propagated from the main, but `counterpart_rate` is **not**. If propagated, the main's rate (A_main→B) would be incorrectly applied to a linked with a different A. Each linked computes its own rate via `_compute_counterpart_rate` in `account_payment_pro`.

### `_get_bundle_journal` fix for outbound

The original implementation used `inbound_payment_method_line_ids` for both inbound and outbound lookups. Fixed to use the correct field based on `payment_type`.

---

## Eliminated/renamed references

| Old reference | New/replacement |
|---------------|----------------|
| `counterpart_exchange_rate` | `counterpart_rate` (Odoo native format) |
| `default_counterpart_exchange_rate` in XML context | Removed (not propagated) |
| `amount_company_currency_signed_pro` | Eliminated |
| `exchange_rate` | `accounting_rate` |
| `counterpart_exchange_rate` field in list view | `user_counterpart_rate` |

---

## Test coverage

Tests are in `tests/test_payment_bundle_multimoneda.py`.

### Bundle multi-currency cases (`TestPaymentBundle`)

| Test | Scenario | Key verification |
|------|----------|-----------------|
| B.1 | Bundle ARS simple (no withholding) | Two linked ARS payments sum to debt |
| B.2 | Bundle ARS with withholding | Linked amounts adjusted after IIBB; payment_difference = 0 |
| B.3 | Mixed: USD debt, linked USD + linked ARS | Each linked computes own `counterpart_rate`; total in B matches |
| B.4 | USD debt, ARS checks + USD transfer | Multiple payment methods; report shows totals in USD (B) |
| B.5 | EUR debt, arbitrage (linked USD + linked ARS) | Cross-currency via C; all expressed in EUR (B) |
| B.6 | Currency consistency constraint | Validates that linked payments must share the same B |
| B.7 | Reconcile mode: ARS journal, USD invoice | Bundle with `reconcile_on_company_currency` |

### Example flow (B.3 — mixed bundle)

```
Invoice: 1.000 USD
Linked 1: 500 USD (A=USD, counterpart_rate=1.0) → 500 USD in B
Linked 2: 600.000 ARS (A=ARS, counterpart_rate≈0.000833) → 500 USD in B
Withholding IIBB: 30 USD (≈36.000 ARS stored)

selected_debt       = 1.000 USD
total_linked_in_b   = 500 + 500 = 1.000 USD
withholdings_amount = 30 USD
payment_difference  = 1.000 - 1.000 - 30 = -30 USD
→ _onchange_withholdings adjusts Linked 2:
  diff_in_a = -30 / 0.000833 = -36.000 ARS
  Linked 2 amount = 600.000 - 36.000 = 564.000 ARS
  Linked 2 counterpart_currency_amount = 564.000 × 0.000833 ≈ 470 USD
→ payment_difference recalculates: 1.000 - (500 + 470) - 30 = 0 ✓
```
