# DESIGN — account_payment_pro

Internal architecture reference for developers maintaining or extending the module.

---

## Tri-currency model

Every payment operates with three explicit currencies:

| Symbol | Field | Description |
|--------|-------|-------------|
| **A** | `currency_id` | Journal / liquidity currency. Native Odoo. |
| **B1** | `counterpart_currency_id` | AP/AR line currency. Computed stored, conditionally editable. |
| **B2** | `destination_currency_id` | UX / reconciliation currency. Computed, **not** stored. |
| **C** | `company_currency_id` | Company accounting currency (ARS for Argentine companies). |

In most cases B1 = B2 (referred to simply as **B**). They differ only when `reconcile_on_company_currency = True`.

### How B1 is determined

```
if destination_account.currency_id exists and ≠ C  → that currency
elif reconcile_on_company_currency                 → C  (editable)
elif to_pay_move_line_ids has lines                → currency of those lines (single-currency constraint)
else                                               → C  (editable)
```

For internal transfers, B1 is fixed to the destination journal's currency.

### How B2 is determined

```
if not reconcile_on_company_currency → B1
else → destination_account.currency_id if ≠ C, else C
```

---

## Exchange rates

### Stored rates (Odoo native format)

Both rates use `_get_conversion_rate(from, to)` = `to / from`, so `amount_from × rate = amount_to`.

| Field | Formula | Example (1 USD = 1200 ARS) |
|-------|---------|----------------------------|
| `accounting_rate` | `_get_conversion_rate(C, A)` = A/C | ≈ 0.000833 |
| `counterpart_rate` | `_get_conversion_rate(A, B1)` = B1/A | 1.0 when A=B |

### UX helpers (non-stored)

`user_accounting_rate` and `user_counterpart_rate` expose the stored rates in a human-readable direction via `compute + inverse`. The direction is decided by `*_rate_inverted` booleans based on the **theoretical** rate (not the user-edited value), so the UI label stays stable during editing.

### Visibility rules

| A | B1 | C | Shown |
|---|----|---|-------|
| ARS | ARS | ARS | None |
| USD | USD | ARS | `accounting_rate` only |
| ARS | USD | ARS | `counterpart_rate` only |
| USD | ARS | ARS | `accounting_rate` only (B1=C, same conversion) |
| USD | EUR | ARS | Both |

When B1 = C, `counterpart_rate` delegates to `accounting_rate` to keep them aligned.

### Rate conversion cheat-sheet

```
C → A:  amount_A = amount_C × accounting_rate
A → C:  amount_C = amount_A / accounting_rate
A → B1: amount_B = amount_A × counterpart_rate
B1→ A:  amount_A = amount_B / counterpart_rate
```

---

## Key fields (post-refactor)

| Field | Currency | Type | Notes |
|-------|----------|------|-------|
| `counterpart_currency_id` | — | Computed stored, editable | B1 |
| `destination_currency_id` | — | Computed non-stored | B2 |
| `accounting_rate` | — | Float stored, editable | Replaces old `exchange_rate` |
| `counterpart_rate` | — | Float stored, editable | Replaces old `counterpart_exchange_rate` (values inverted) |
| `counterpart_currency_amount` | B1 | Monetary stored + inverse | Amount in B |
| `selected_debt` | B2 | Computed | Was in C |
| `to_pay_amount` | B2 | Computed + inverse | Was in C |
| `write_off_amount` | B2 | Monetary | Was in C (migrated) |
| `payment_total` | B2 | Computed | Was in C |
| `payment_difference` | B2 | Computed | Was in C |
| `matched_amount` | B2 | Computed | Was in C |
| `unmatched_amount` | B2 | Computed | Was in C |
| `to_pay_amount_company_currency` | C | Computed | New |

### Eliminated fields

| Old field | Replacement |
|-----------|-------------|
| `exchange_rate` | `accounting_rate` (Odoo native format) |
| `counterpart_exchange_rate` | `counterpart_rate` (values inverted) |
| `force_amount_company_currency` | `accounting_rate` |
| `amount_company_currency` | `amount / accounting_rate` |
| `amount_company_currency_signed_pro` | Compute from `payment_type`/`partner_type` + `amount / accounting_rate` |
| `other_currency` | `currency_id != company_currency_id` |

---

## Journal entry generation (`_prepare_move_lines_per_type`)

- Liquidity line: `currency_id = A`, `amount_currency` in A, `balance = amount / accounting_rate`.
- Counterpart line: `currency_id = B1`, `amount_currency` in B, balance squares by difference.
- Write-off line: `destination_currency_id` with conversion to C via `_convert()`.
- When `force_balance` is set (paired internal transfer), the liquidity balance is **not** recalculated from `accounting_rate` to avoid rounding discrepancies in cross-currency transfers (e.g. USD → EUR).
- **Write-off + withholding coexistence:** Base Odoo discards `write_off_lines` when `withholding_lines` exist. The override re-injects write-off lines and rebalances the counterpart.

### Internal transfers

The bridge-account (counterpart) line is always in company currency (C) with `amount_currency = balance`. This ensures both sides (original + paired) share the same currency on the bridge account and can reconcile on both `amount_currency` and `balance`.

The paired payment's `accounting_rate` is set to the **implicit real rate** of the operation (not the day's rate), avoiding rounding discrepancies.

---

## Design decisions (ADRs)

### ADR-001 — Tri-currency model instead of pivoting on company_currency

The old module used `company_currency_id` as the pivot for nearly all UX, making bi-currency payments impossible. The refactor introduces three explicit currencies (A, B, C).

### ADR-002 — `destination_currency_id` is not stored

It is derived from `counterpart_currency_id` and `reconcile_on_company_currency`. Storing it would create inconsistencies when the destination account or debt lines change.

### ADR-003 — B1 editable only in specific cases

Only editable when the account has no forced currency (or it equals C) AND (`reconcile_on_company_currency` is active OR no debts selected). In internal transfers it is not editable (determined by the destination journal).

### ADR-004 — `accounting_rate` replaces `force_amount_company_currency`

The old boolean + amount coupling was replaced by a direct rate field in Odoo native format (`A/C`), consistent with how Odoo handles rates elsewhere.

### ADR-006 — Single-currency constraint via Python

`@api.constrains` validates that all selected debt lines share the same currency (unless `reconcile_on_company_currency` is active). Not a SQL constraint because the condition depends on a company setting.

### ADR-007 / ADR-011 — Rates in Odoo format, stable UI direction

Stored rates use Odoo native format. UX helpers invert conditionally. The `*_rate_inverted` booleans are based on the **theoretical** rate so the label direction doesn't flip while the user types through 1.0.

### ADR-008 — `counterpart_rate` migration inverted existing values

`counterpart_exchange_rate` stored user-friendly values (e.g. 1500). The migration inverts them to Odoo native format (e.g. 0.000667) via `SET counterpart_rate = 1.0 / counterpart_rate`.

### ADR-009 — Migration prevents mass recompute

`pre_migrate.py` populates all new/renamed stored columns via SQL before the ORM loads the new module definition, preventing Odoo from enqueuing recomputes for thousands of historical payments.

### ADR-010 — `write_off_amount` migrated to `destination_currency_id`

The migration script backs up the original column and converts values using `counterpart_rate`.

---

## Migration scripts (19.0.2.0.0)

### `pre_migrate.py`

1. **Backup** all modified columns (`counterpart_exchange_rate`, `force_amount_company_currency`, `amount_company_currency`, `write_off_amount`) via `openupgrade.copy_columns`.
2. **Rename** `counterpart_exchange_rate` → `counterpart_rate` + invert values (`1.0 / rate`).
3. **Create** `accounting_rate` column, populate from `amount / amount_company_currency` (or 1.0).
4. **Convert** `write_off_amount` from C to B via `/ counterpart_rate`.

### `post_migrate.py`

Verification: zero posted payments with NULL `accounting_rate` or `counterpart_rate`.

---

## Test coverage

Tests are in `tests/test_payment_multimoneda.py` and `tests/test_internal_transfer_multimoneda.py`.

### Payment multi-currency cases (`TestPaymentMultimoneda`)

These tests validate the full lifecycle (creation → rate setting → posting → journal entry verification) for each currency combination:

| Test | Scenario | Currencies A→B→C |
|------|----------|-----------------|
| Caso 1 | Local (no conversion) | ARS→ARS→ARS |
| Caso 2 | Pure foreign currency | USD→USD→ARS |
| Caso 3 | Foreign currency purchase | ARS→USD→ARS |
| Caso 4 | Foreign currency sale | USD→ARS→ARS |
| Caso 5 | Cross-currency arbitrage | USD→EUR→ARS |
| Caso 6 | Partial / mixed payment | ARS→USD→ARS |
| Caso 7 | Advance payment (no debt) | ARS→USD→ARS |
| Caso 8 | Reconcile on company currency (ARS journal, USD forced) | ARS / B1=USD / B2=ARS |
| Caso 9 | USD journal, ARS debt with reconcile | USD / B1=USD / B2=ARS |
| Caso 10 | Arbitrage with reconcile | EUR / B1=USD / B2=ARS |

Additional unit tests cover: rate sync when B1=C, `counterpart_currency_amount` inverse, `selected_debt` field selection, rate visibility rules, and write-offs (company and foreign currency).

### Check payment cases (`TestPaymentChecks`)

| Test | Scenario |
|------|----------|
| TC1 | Two checks, local currency |
| TC2 | Three checks, pure foreign currency |
| TC3 | Two checks, foreign currency purchase |
| TC4 | Two checks with write-off |
| TC5 | Check with write-off, foreign currency purchase |

### Internal transfer cases (`TestInternalTransferMultimoneda`)

| Test | Transfer | Key verification |
|------|----------|-----------------|
| IT.1 | ARS → ARS | Trivial, no conversion |
| IT.2 | ARS → USD | Buy foreign currency; paired `accounting_rate` = market rate |
| IT.3 | USD → ARS | Sell foreign currency (inverse of IT.2) |
| IT.4 | USD → EUR | Cross-currency via C; bridge balances match; no amount_currency reconciliation |
| IT.5 | ARS → USD (custom rate) | User-edited rate; paired amount respects it |
| IT.6 | EUR → ARS | Another currency combination |
