# Spec: l10n_ar_tax — Retenciones en pagos multimoneda (B!=C)

**Módulo:** `l10n_ar_tax` (ADHOC)
**Depende de:** `account_payment_pro` refactor (T-62550) — requiere `destination_currency_id`, `accounting_rate`, `counterpart_rate`
**Estado:** Implementado

---

## Contexto y motivación

Actualmente el módulo muestra un `withholding_warning` cuando el pago involucra
moneda extranjera en la deuda (B!=C), porque el cálculo de retenciones no estaba
preparado para ese escenario. El refactor de `account_payment_pro` introduce
`destination_currency_id` (moneda B), lo que habilita implementar el soporte correcto.

**Principio fiscal:**
Las retenciones en Argentina se calculan y almacenan **siempre en ARS (C)**.
`compute_all` siempre recibe ARS. El `amount` en la withholding line siempre es ARS.
El usuario ve los montos en la moneda de la deuda (B) solo a efectos de UX —
para saber cuánto neto transferir.

**Principio de tasa:**
La base imponible se convierte B->C usando el **rate del pago** (no el rate spot
del día ni el rate histórico de la factura).

---

## Decisión de diseño clave: `base_amount` siempre en C (ARS)

> **`base_amount` se mantiene en ARS (C), NO migra a moneda B.**

### Justificación

1. **AFIP exige ARS.** Los certificados de retención muestran ARS; `compute_all` recibe ARS.
2. **`same_period_base` ya está en ARS.** Los move lines acumulan `balance` en ARS (C).
   `C + C = C` sin conversión — coherente y directo.
3. **El usuario edita la base en ARS** — intuitivo en el contexto impositivo argentino.
4. **No requiere script de migración** — la columna `base_amount` en PG mantiene su semántica.
5. **Simplifica `_tax_compute_all_helper`** — recibe la base ya en C, no necesita
   conversión interna.

---

## Alcance

**Entra:**
- Helper `_get_withholding_rate()` en `account.payment` (B->C usando rates del pago)
- Cambiar `currency_field` de `selected_debt_untaxed` a `destination_currency_id`
- Adaptar `_compute_selected_debt_untaxed` para usar `amount_residual_currency` cuando B!=C
- Adaptar `_tax_compute_all_helper`: `base_amount` ya llega en C — usarlo directamente en `compute_all` sin conversión
- Adaptar `_prepare_move_withholding_lines`: reemplazar `self.exchange_rate` por `self.accounting_rate`
- Adaptar `_compute_payment_total` para sumar `withholdings_amount` (B) al total en B
- Cambiar `currency_field` de `withholdings_amount` a `destination_currency_id` con conversión C->B
- Eliminar `withholding_warning` y `_compute_withholding_warning`
- Tests para los casos documentados

**No entra:**
- Cambios en `_get_same_period_base_amount` / `_get_same_period_withholdings_amount`
  (acumulan `balance` de move lines que ya está en ARS, sin impacto)

---

## Convención de rates — referencia rápida

`_get_conversion_rate(from, to)` devuelve un multiplicador: `amount_from * rate = amount_to`.

Para compañía argentina (C=ARS):

| Par | _get_conversion_rate | Ejemplo (1 USD = 1200 ARS) |
|-----|---------------------|---------------------------|
| USD -> ARS | 1200 | 100 USD * 1200 = 120.000 ARS |
| ARS -> USD | 0.000833 | 120.000 ARS * 0.000833 = 100 USD |
| ARS -> ARS | 1.0 | trivial |

Los campos stored del pago usan este formato:
- `accounting_rate` = `_get_conversion_rate(A, C)` — si A=USD, C=ARS: **1200**
- `counterpart_rate` = `_get_conversion_rate(A, B1)` — si A=ARS, B1=USD: **0.000667** (a rate 1500)

---

## Cambios en `account.payment`

### `_get_withholding_rate()` — nuevo método

Devuelve **multiplicador directo** `base_B * rate = amount_C`.
Fórmula general: `accounting_rate / counterpart_rate`.

```python
def _get_withholding_rate(self):
    """Tasa efectiva B->C para convertir base de retención a ARS.
    Devuelve multiplicador directo: base_in_B * rate = base_in_C.
    Ejemplo: B=USD, C=ARS, rate=1200 -> 100 USD * 1200 = 120.000 ARS.

    Fórmula general: accounting_rate / counterpart_rate
    Esto funciona para todos los casos:
      B==C: accounting/counterpart = X/X = 1.0
      B==A: accounting/1.0 = accounting_rate (A->C)
      A==C: 1.0/counterpart = 1/counterpart_rate (invierte A->B para obtener B->C)
      Arbitraje: accounting/counterpart (transitividad)
    """
    self.ensure_one()
    counterpart = self.counterpart_rate or 1.0
    accounting = self.accounting_rate or 1.0
    return accounting / counterpart if counterpart else 1.0
```

### `_compute_withholdings_amount` — conversión C->B para UX

```python
withholdings_amount = fields.Monetary(
    compute="_compute_withholdings_amount",
    currency_field="destination_currency_id",
)

@api.depends("l10n_ar_withholding_line_ids.amount")
def _compute_withholdings_amount(self):
    for rec in self:
        total_ars = sum(rec.l10n_ar_withholding_line_ids.mapped("amount"))
        rate = rec._get_withholding_rate()
        rec.withholdings_amount = (
            rec.destination_currency_id.round(total_ars / rate) if rate else 0.0
        )
```

### `_compute_payment_total` — sumar withholdings en B

`payment_total` ahora es en B (`destination_currency_id`). `withholdings_amount` ya
está convertido a B. Reemplazar la suma de `line.amount` (C) por `withholdings_amount` (B):

```python
@api.depends("l10n_ar_withholding_line_ids.amount")
def _compute_payment_total(self):
    super()._compute_payment_total()
    for rec in self.filtered("l10n_ar_withholding_line_ids"):
        if (rec.payment_type == "outbound" and rec.partner_type == "customer") or (
            rec.payment_type == "inbound" and rec.partner_type == "supplier"
        ):
            sign = -1
        else:
            sign = 1
        rec.payment_total += sign * rec.withholdings_amount
```

### `_compute_withholding_warning` — eliminar

Borrar el campo `withholding_warning` y todo el método `_compute_withholding_warning`.
Borrar también el div de warning en la vista XML.

### `selected_debt_untaxed` — migrar a B

```python
selected_debt_untaxed = fields.Monetary(
    compute="_compute_selected_debt_untaxed",
    currency_field="destination_currency_id",
)

@api.depends("to_pay_move_line_ids", "destination_currency_id", "company_currency_id")
def _compute_selected_debt_untaxed(self):
    for rec in self:
        selected_debt_untaxed = 0.0
        for line in rec.to_pay_move_line_ids._origin:
            factor = line.move_id._get_tax_factor() if line.move_id else 1.0
            if rec.destination_currency_id and rec.destination_currency_id != rec.company_currency_id:
                selected_debt_untaxed += line.amount_residual_currency * factor
            else:
                selected_debt_untaxed += line.amount_residual * factor
        rec.selected_debt_untaxed = selected_debt_untaxed * (
            -1.0 if rec.partner_type == "supplier" else 1.0
        )
```

### `withholdable_advanced_amount` — cambiar currency_field

Solo cambio de declaración:

```python
withholdable_advanced_amount = fields.Monetary(
    "Adjustment / Advance (untaxed)",
    help="Used for withholdings calculation",
    currency_field="destination_currency_id",
    compute="_compute_withholdable_advanced_amount",
    copy=False, store=True, readonly=False,
)
```

---

## Cambios en `l10n_ar.payment.withholding`

### Campos

```python
# currency_id en C (ARS) — para amount y base_amount
currency_id = fields.Many2one(related="payment_id.company_currency_id")

# base_amount en C (ARS) — NO existe base_currency_id
base_amount = fields.Monetary(
    currency_field="currency_id",  # C (ARS)
    compute="_compute_base_amount",
    store=True, readonly=False,
)

# amount en C (ARS) — sin cambios
amount = fields.Monetary(
    currency_field="currency_id",
    compute="_compute_amount",
    store=True, readonly=False,
)
```

### `_compute_base_amount` — calcular base en B, convertir a C al final

Los campos de deuda (`selected_debt`, `selected_debt_untaxed`, etc.) están en B.
Se suman en B y al final se convierte con `_get_withholding_rate()`. Fix de comparación
pago parcial: usar `amount_residual_currency` cuando B≠C.

```python
@api.depends(...)
def _compute_base_amount(self):
    self.payment_id._compute_to_pay_amount()
    for wth in self.filtered(lambda x: x.payment_id.partner_type == "supplier"):
        pay = wth.payment_id
        advance_amount = pay.withholdable_advanced_amount  # en B
        tax = wth._get_withholding_tax()
        if advance_amount < 0.0 and pay.to_pay_move_line_ids:
            sorted_to_pay_lines = sorted(
                pay.to_pay_move_line_ids,
                key=lambda a: a.date_maturity or a.date,
            )
            partial_line = sorted_to_pay_lines[-1]

            # Comparar en moneda B (ambos lados)
            if pay.destination_currency_id != pay.company_currency_id:
                line_residual = abs(partial_line.amount_residual_currency)
            else:
                line_residual = abs(partial_line.amount_residual)

            if line_residual < abs(pay.withholdable_advanced_amount):
                raise UserError(...)

            advance_amount = pay.unreconciled_amount  # B
            if tax.l10n_ar_tax_type != "iibb_total":
                advance_amount = advance_amount * (
                    pay.selected_debt_untaxed / pay.selected_debt
                )

        # Calcular base en B (campos en B)
        if tax.l10n_ar_tax_type == "iibb_total":
            base_in_b = pay.selected_debt + advance_amount
        else:
            base_in_b = pay.selected_debt_untaxed + advance_amount

        # Convertir B → C al final usando rate del pago
        wth.base_amount = pay.company_currency_id.round(
            base_in_b * pay._get_withholding_rate()
        )

    # ratio handling (opera sobre C, resultado sigue en C)
    for wth in self.filtered(lambda x: x.tax_id.amount_type == "percent" and x.tax_id.ratio != 100):
        wth.base_amount *= wth.tax_id.ratio / 100
```

### `_tax_compute_all_helper` — `base_amount` ya en C, compute_all en ARS

`base_amount` llega en C (ARS) desde `_compute_base_amount`. No se necesita conversión.
Se elimina `base_in_c` y se usa `self.base_amount` directamente:

```python
def _tax_compute_all_helper(self):
    self.ensure_one()
    tax = self._get_withholding_tax()
    if not tax.amount_type:
        raise UserError(...)

    pay = self.payment_id
    company_currency = pay.company_currency_id

    # base_amount ya está en C (ARS) — no se necesita conversión
    if tax.l10n_ar_tax_type in ["earnings", "earnings_scale"]:
        same_period_withholdings = self._get_same_period_withholdings_amount()
        same_period_base = self._get_same_period_base_amount()
        net_amount = self.base_amount + same_period_base  # C + C = C
    else:
        net_amount = self.base_amount

    net_amount = max(0, net_amount - tax.l10n_ar_non_taxable_amount)

    # compute_all SIEMPRE en ARS (C)
    taxes_res = tax.compute_all(
        net_amount,
        currency=company_currency,
        quantity=1.0,
        product=False,
        partner=False,
        is_refund=False,
    )
    tax_amount = company_currency.round(
        taxes_res["total_included"] - taxes_res["total_excluded"]
    )
    tax_account_id = taxes_res["taxes"][0]["account_id"]
    tax_repartition_line_id = taxes_res["taxes"][0]["tax_repartition_line_id"]

    # Ref: formatear en ARS (self.base_amount, same_period_base, etc.)
    ref = False
    f = company_currency.format
    if tax.l10n_ar_tax_type in ["earnings", "earnings_scale"]:
        if net_amount <= 0:
            ref = (
                f"{f(self.base_amount)} + {f(same_period_base)}"
                f" - {f(tax.l10n_ar_non_taxable_amount)}"
                f" = {f(self.base_amount + same_period_base - tax.l10n_ar_non_taxable_amount)}"
                f" (no corresponde aplicar)"
            )
        if tax.l10n_ar_tax_type == "earnings_scale":
            # ... escala logic sin cambios, opera sobre net_amount (C)
            ...
            ref = ref or (
                f"({f(self.base_amount)} + {f(same_period_base)}"
                f" - {f(tax.l10n_ar_non_taxable_amount)}"
                f" - {f(escala.excess_amount)})"
                f" * {escala.percentage}%"
                f" + {f(escala.fixed_amount)}"
                f" - {f(same_period_withholdings)}"
            )
        else:
            ref = (
                f"({f(self.base_amount)} + {f(same_period_base)}"
                f" - {f(tax.l10n_ar_non_taxable_amount)})"
                f" * {tax.amount}%"
                f" - {f(same_period_withholdings)}"
            )
        tax_amount -= same_period_withholdings

    if tax.l10n_ar_minimum_threshold > tax_amount:
        tax_amount = 0.0
    return tax_amount, tax_account_id, tax_repartition_line_id, ref
```

**No existe `base_in_c` ni `withholding_rate` en este método.**
`self.base_amount` ya es ARS cuando llega aquí.

### `_prepare_move_withholding_lines` — fix trivial

Reemplazar `self.exchange_rate` (eliminado) por `self.accounting_rate`:

```python
# Antes (línea 144):
conversion_rate = self.exchange_rate or 1.0
# Después:
conversion_rate = self.accounting_rate or 1.0
```

La fórmula `amount_currency = balance / conversion_rate` sigue funcionando igual
porque `accounting_rate` tiene el mismo valor numérico que tenía `exchange_rate`
(`_get_conversion_rate(A, C)` = multiplicador A->C).

Ejemplo: A=USD, C=ARS, rate=1200. Balance=36.000 ARS.
`amount_currency = 36.000 / 1200 = 30 USD` (en moneda A para el journal entry) ✓

---

## Cambios en vista XML

Eliminar el div de `withholding_warning`:

```xml
<!-- ELIMINAR -->
<div class="alert alert-warning" role="alert" invisible="not withholding_warning">
    Atención: La deuda se está cancelando en moneda extranjera...
</div>
```

---

## Casos de test

Convención: A=moneda diario, B=destination_currency, C=ARS.
Factor IVA 21% -> `_get_tax_factor()` = 1/1.21 ~ 0.8264.
Retención ejemplo: 3% sobre base neta sin IVA.

---

### T.1 — Pago local (A=B=C=ARS)

**Setup:** Factura 1.210 ARS (1.000 neto + 210 IVA). Pago 1.210 ARS.
- accounting_rate = 1.0, counterpart_rate = 1.0

**Cálculo:**
```
selected_debt_untaxed = 1.210 * (1/1.21) = 1.000 ARS
_get_withholding_rate = 1.0/1.0 = 1.0
base_amount           = 1.000 * 1.0 = 1.000 ARS  ← C (stored)
withholding amount    = 1.000 * 3% = 30 ARS (stored en C)
withholdings_amount   = 30 / 1.0 = 30 ARS (UX en B=C)
```

---

### T.2 — Pago divisa pura (A=B=USD, C=ARS, 1 USD = 1.200 ARS)

**Setup:** Factura 1.210 USD (1.000 neto + 210 IVA). Pago 1.210 USD.
- accounting_rate = 1200 (= `_get_conversion_rate(USD, ARS)`)
- counterpart_rate = 1.0 (A=B)

**Cálculo:**
```
selected_debt_untaxed = 1.210 * (1/1.21) = 1.000 USD  (usa amount_residual_currency)
_get_withholding_rate = 1200/1.0 = 1200
base_amount           = 1.000 * 1200 = 1.200.000 ARS  ← C (stored)
withholding amount    = 1.200.000 * 3% = 36.000 ARS (stored)
withholdings_amount   = 36.000 / 1200 = 30 USD (UX)
```

**Asiento retención:**
balance=36.000 ARS, amount_currency = 36.000/1200 = 30 USD, currency_id=USD(A)

---

### T.3 — Compra de divisa (A=C=ARS, B=USD, 1 USD = 1.500 ARS)

**Setup:** Factura 1.210 USD (1.000 neto + 210 IVA). Pago en ARS.
- accounting_rate = 1.0 (A=C)
- counterpart_rate = 0.000667 (= `_get_conversion_rate(ARS, USD)` = 1/1500)

**Cálculo:**
```
selected_debt_untaxed = 1.000 USD (amount_residual_currency)
_get_withholding_rate = 1.0/0.000667 = 1500
base_amount           = 1.000 * 1500 = 1.500.000 ARS  ← C (stored)
withholding amount    = 1.500.000 * 3% = 45.000 ARS (stored)
withholdings_amount   = 45.000 / 1500 = 30 USD (UX)
```

**Asiento retención:**
balance=45.000 ARS, amount_currency = 45.000/1.0 = 45.000 ARS, currency_id=ARS(A)

---

### T.4 — Dos facturas USD a distintos rates, pago a rate diferente

**Setup:** A=C=ARS, B=USD, counterpart_rate=0.000667 (1 USD = 1.500 ARS)
- Factura 1: 1.210 USD (1.000 neto), rate original 1.000
- Factura 2: 1.210 USD (1.000 neto), rate original 1.100

**Cálculo:**
```
selected_debt_untaxed = (1.210 + 1.210) * (1/1.21) = 2.000 USD
_get_withholding_rate = 1500
base_amount           = 2.000 * 1500 = 3.000.000 ARS  ← C (stored)
withholding amount    = 3.000.000 * 3% = 90.000 ARS
withholdings_amount   = 90.000 / 1500 = 60 USD
```

**Clave:** NO se calcula por factura con rate histórico (1.000*1000 + 1.000*1100 = 2.100.000).
Se usa el rate del pago sobre el total. Correcto fiscalmente.

---

### T.5 — Pago parcial (A=C=ARS, B=USD)

**Setup:** Factura 2.420 USD (2.000 neto). counterpart_rate=0.000667 (1 USD = 1.500).
Usuario paga solo 750.000 ARS -> contrapartida = 750.000 * 0.000667 = 500 USD.
- selected_debt = 2.420 USD
- to_pay_amount = 500 USD
- unreconciled_amount = 500 - 2.420 = -1.920 USD
- withholdable_advanced_amount = -1.920 USD

**Cálculo:**
```
advance_amount = unreconciled_amount * (selected_debt_untaxed / selected_debt)
               = -1.920 * (2.000 / 2.420) = -1.586,78 USD
base_in_b      = 2.000 + (-1.586,78) = 413,22 USD
base_amount    = 413,22 * 1500 = 619.835 ARS  ← C (stored)
withholding    = 619.835 * 3% = 18.595 ARS
UX             = 18.595 / 1500 ~ 12,40 USD
```

---

### T.6 — Arbitraje (A=USD, B=EUR, C=ARS)

**Setup:** Factura 1.210 EUR (1.000 neto). Pago en USD.
- 1 USD = 1.200 ARS, 1 EUR = 1.320 ARS
- accounting_rate = 1200 (`_get_conversion_rate(USD, ARS)`)
- counterpart_rate = 0.909 (`_get_conversion_rate(USD, EUR)` = 1200/1320)

**Cálculo:**
```
selected_debt_untaxed = 1.000 EUR
_get_withholding_rate = 1200 / 0.909 = 1320  (EUR->ARS, correcto!)
base_amount           = 1.000 * 1320 = 1.320.000 ARS  ← C (stored)
withholding amount    = 1.320.000 * 3% = 39.600 ARS
withholdings_amount   = 39.600 / 1320 = 30 EUR
```

**Asiento retención:**
balance=39.600 ARS, amount_currency = 39.600/1200 = 33 USD, currency_id=USD(A)

---

### T.7 — Ganancias con acumulado del período (A=C=ARS, B=USD)

**Setup:** Ya hay retenciones del mismo régimen en el período por 500.000 ARS (base) y 15.000 ARS (retenido).
Factura nueva: 1.210 USD (1.000 neto). counterpart_rate=0.000667 (1 USD = 1500).
Retención ganancias: 7% sobre base, mínimo no imponible 100.000 ARS.

**Cálculo:**
```
_get_withholding_rate = 1500
base_amount         = 1.000 * 1500 = 1.500.000 ARS  ← C (stored)
same_period_base    = 500.000 ARS  (de move lines, ya en C)
net_amount          = 1.500.000 + 500.000 - 100.000 = 1.900.000 ARS  (C + C, correcto)
withholding         = 1.900.000 * 7% = 133.000 ARS
                    - same_period_withholdings 15.000 = 118.000 ARS
withholdings_amount = 118.000 / 1500 ~ 78,67 USD
```

---

## Mapa completo de cambios por archivo

### `account_payment.py` (en l10n_ar_tax)

| Cambio | Detalle |
|--------|---------|
| `_get_withholding_rate()` | Nuevo método |
| `withholdings_amount` | currency_field -> `destination_currency_id`, compute con conversión C->B |
| `_compute_payment_total` | Sumar `withholdings_amount` (B) en vez de `sum(line.amount)` (C) |
| `withholding_warning` | Eliminar campo |
| `_compute_withholding_warning` | Eliminar método |
| `selected_debt_untaxed` | currency_field -> `destination_currency_id`, adaptar compute |
| `withholdable_advanced_amount` | currency_field -> `destination_currency_id` |
| `_prepare_move_withholding_lines` | `self.exchange_rate` -> `self.accounting_rate` |
| `_use_counterpart_currency()` | Ya eliminado en payment_pro, limpiar referencia en warning |

### `l10n_ar_payment_withholding.py`

| Cambio | Detalle |
|--------|---------|
| `base_amount` | `currency_field="currency_id"` (C/ARS); `_compute_base_amount` convierte B→C al final |
| `currency_id` | Se mantiene en `company_currency_id` (para `amount` y `base_amount`) |
| `amount` | Sin cambios (se mantiene en C) |
| `_compute_base_amount` | Calcula `base_in_b` en B, convierte a C con `_get_withholding_rate()`; fix comparación pago parcial |
| `_tax_compute_all_helper` | `base_amount` ya en C — `compute_all` con `currency=company_currency_id`, ref en ARS; sin `base_in_c` |

### `account_payment_view.xml` (en l10n_ar_tax)

| Cambio | Detalle |
|--------|---------|
| Warning div | Eliminar |

---

## Campos eliminados (no deben buscarse en el código)

| Campo | Reemplazado por |
|-------|-----------------|
| `exchange_rate` | `accounting_rate` |
| `other_currency` | `currency_id != company_currency_id` |
| `force_amount_company_currency` | eliminado (lógica simplificada) |
| `amount_company_currency` | eliminado |
| `amount_company_currency_signed_pro` | eliminado |
| `withholding_warning` | eliminado (soporte real B!=C) |
| `base_currency_id` | **nunca fue** — `base_amount` siempre en C |

---

## Criterios de aceptación

- [ ] Los 7 casos de test tienen test de integración
- [ ] `withholding_warning` eliminado de modelo y vista
- [ ] `selected_debt_untaxed` usa `amount_residual_currency` cuando B!=C
- [ ] `base_amount` se almacena en ARS (C) — verificar en shell con `payment.l10n_ar_withholding_line_ids[0].base_amount`
- [ ] Para pago USD 100 a 1200 ARS/USD con IIBB 3%: `base_amount = 120.000`, `amount = 3.600`
- [ ] Para pago ARS 120.000 (sin conversión): `base_amount = 120.000`, `amount = 3.600`
- [ ] `amount` se mantiene en C (ARS)
- [ ] `_tax_compute_all_helper` pasa `currency=company_currency_id` (C) a `compute_all`
- [ ] `_tax_compute_all_helper` usa `self.base_amount` (ya en C) directamente; NO existe `base_in_c`
- [ ] `_get_withholding_rate` cubre los 4 casos (formula general `accounting_rate / counterpart_rate`)
- [ ] Los asientos de retención mantienen `balance` en ARS
- [ ] `_prepare_move_withholding_lines` usa `self.accounting_rate` en vez de `self.exchange_rate`
- [ ] `_compute_payment_total` suma `withholdings_amount` (B) al total en B
- [ ] Ganancias: `net_amount = self.base_amount + same_period_base` (ambos en C, sin conversión)
- [ ] Ref string formatea montos en ARS usando `company_currency.format`
- [ ] No existe `base_currency_id` como campo de `l10n_ar.payment.withholding`

---

## Nota: corrección en spec_final.md de payment_pro

Los ejemplos de formato Odoo nativo en la spec de payment_pro usan "ej: 0.000667" para
`accounting_rate`. Esto es engañoso: 0.000667 aplica cuando A es la moneda débil (ARS->USD).
Cuando A=USD y C=ARS, `accounting_rate = 1200`.

Corregir el ejemplo a: "formato Odoo nativo (ej: 1200 para USD->ARS, o 1.0 cuando A=C)".

---

## Impacto en otros módulos

| Módulo | Tipo | Acción |
|--------|------|--------|
| `account_payment_pro` | Dependencia: requiere `destination_currency_id`, `accounting_rate`, `counterpart_rate` | No implementar antes de T-62550 |
| Reportes SICORE/SIFERE | Sin impacto: usan `amount` (ARS) de las withholding lines | Verificar que no lean `withholdings_amount` |
| `report_withholding_certificate` | Sin impacto esperado: muestra `amount` (ARS) | Verificar render con pagos multimoneda |
