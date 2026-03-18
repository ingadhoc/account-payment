# Account Payment Pro

Extends Odoo's core payment model to support multi-currency operations, debt selection, withholdings, and write-offs. Introduces a **tri-currency model** (A / B / C) that cleanly separates the journal currency, the debt/cancellation currency, and the company accounting currency.

This module is the foundation for managing Argentine withholdings — install `l10n_ar_tax` (and `l10n_ar_withholding`) to activate that feature.

## Features

- **Tri-currency payments:** work with up to three currencies per payment — journal (A), counterpart/debt (B), and company (C).
- **Select debts to pay:** choose specific invoices or credit notes during payment creation.
- **Withholding support:** dedicated tab for tax withholdings when the localization module is installed.
- **Write-offs:** register write-offs directly within the payment form.
- **Editable exchange rates:** `accounting_rate` (A↔C) and `counterpart_rate` (A↔B) are stored and user-editable; the UI shows rates in the most readable direction automatically.
- **Multi-currency internal transfers:** supports transfers between journals in different currencies (ARS→USD, USD→EUR, etc.) with proper bridge-account reconciliation.
- **Pay Now on invoices:** instant payment creation from the invoice form.

## Dependencies

| Module | Purpose |
|--------|---------|
| `account` | Odoo core accounting |
| `l10n_latam_invoice_document` | LATAM invoice documents |
| `account_internal_transfer` | Internal transfer support |
| `l10n_latam_check` | Check management |
| `account_ux` | Provides `reconcile_on_company_currency` on `res.company` |

For Argentine withholdings: install `l10n_ar_withholding` + `l10n_ar_tax`.

## Configuration

1. **Write-off types:** Accounting → Configuration → Write-off Types.
2. **Payment settings:** Accounting → Configuration → Settings → Payment.
3. **Reconcile on company currency:** enable per-company in Accounting → Settings if you need AP/AR accounts without a specific currency to always reconcile in the company currency.

## Usage

1. Go to Accounting → Payments to create and manage payments.
2. Use "Pay Now" on invoices for quick payment processing.
3. Select specific debts, adjust exchange rates, register withholdings and write-offs in the payment form.
4. Internal transfers between different-currency journals are created normally; the system computes paired amounts and rates automatically.

## Bug Tracker

Bugs are tracked on [GitHub Issues](https://github.com/ingadhoc/account-payment/issues).

## Credits

**Author:** ADHOC SA · [www.adhoc.com.ar](https://www.adhoc.com.ar)
**License:** AGPL-3.0 or later

---

See [DESIGN.md](DESIGN.md) for internal architecture and design decisions.
