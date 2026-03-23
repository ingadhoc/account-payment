# Spec: l10n_ar_payment_bundle — Adaptación al modelo tri-monetario + soporte multimoneda

**Módulo:** `l10n_ar_payment_bundle` (ADHOC)
**Depende de:** `account_payment_pro` refactor (T-62550) + `l10n_ar_tax` refactor
**Issue:** T-XXXXX
**Autor:** Juan
**Fecha:** 2025-03-18 (rev. final)
**Estado:** Borrador

---

## Contexto

El módulo `l10n_ar_payment_bundle` permite crear "recibos bundle": un pago principal
(`is_main_payment=True`, amount=0) que agrupa pagos vinculados (`link_payment_ids`)
de distintos diarios/métodos. El pago principal concentra la deuda, retenciones y
write-off; los pagos vinculados son los medios de pago reales.

### Problemas actuales

1. **Restricción ARS-only:** Los pagos vinculados solo pueden usar diarios sin moneda
   (línea 87: `not j.currency_id`), lo que impide pagar con diarios en USD, EUR, etc.

2. **Breaking changes del refactor:** Campos renombrados (`counterpart_exchange_rate` →
   `counterpart_rate`), eliminados (`amount_company_currency_signed_pro`, `exchange_rate`)
   y con moneda cambiada (`payment_total`, `selected_debt`, `withholdings_amount`,
   `write_off_amount`, `payment_difference` → todos ahora en `destination_currency_id`).

3. **Mezcla de monedas en `_compute_payment_difference`:** Usa
   `amount_company_currency_signed` (C) pero lo resta de `selected_debt` (B) — produce
   resultados incorrectos cuando B ≠ C.

4. **Conversión innecesaria en `_compute_counterpart_currency_amount`:** Divide por
   `counterpart_exchange_rate` cuando `withholdings_amount` y `write_off_amount` ya
   están en B tras el refactor.

---

## Principios de diseño

> **P1 — El pago principal define la moneda de cancelación (B).**
> `counterpart_currency_id` y `destination_currency_id` del main determinan en qué
> moneda se expresa la deuda, los totales y las diferencias.

> **P2 — Los pagos vinculados heredan B del principal; no lo pueden editar.**
> `counterpart_currency_id` se propaga via default en el contexto y es readonly en la
> vista de linked. Cada linked computa su propio `counterpart_rate` (A→B) según su
> diario, no lo hereda del main.

> **P3 — Cualquier diario es válido para pagos vinculados.**
> Se elimina la restricción `not j.currency_id`. Un bundle puede mezclar pagos en
> ARS, USD, EUR, etc. Todos se expresan en B vía `counterpart_currency_amount`.

---

## Alcance

**Entra:**
- Eliminar restricción de diarios sin moneda para pagos vinculados
- Adaptar todas las referencias a campos renombrados/eliminados
- Reescribir `_compute_counterpart_currency_amount` para main_payment
- Reescribir `_compute_payment_difference` para linked payments (operar en B)
- Adaptar `_onchange_withholdings` para convertir B→A en linked payments
- No propagar `counterpart_rate` como default — dejar que cada linked lo compute
- Adaptar `bundle_counterpart_currency_amount` al nuevo currency_field
- Adaptar vistas (XML) a campos renombrados
- Corregir report template (monedas de display)
- Limpiar código comentado obsoleto
- Fix bug en `_get_bundle_journal` para outbound

**No entra:**
- Cambios funcionales nuevos más allá de la adaptación y el desbloqueo multimoneda
- Soporte para linked payments con distinto `destination_currency_id` entre sí
  (todos comparten el B del main)

---

## Convención de monedas (referencia rápida)

Mismo modelo tri-monetario de `account_payment_pro`:

| Símbolo | Campo | En el bundle |
|---------|-------|-------------|
| **A** | `currency_id` | Moneda del diario de cada pago. Puede diferir entre main y linked. |
| **B** | `destination_currency_id` | Moneda de cancelación. Definida por el main, heredada por todos. |
| **C** | `company_currency_id` | ARS. Siempre la misma para todos. |

**Rates por pago vinculado:**
- `counterpart_rate` = `_get_conversion_rate(A_linked, B)` — cada linked tiene el suyo
- `accounting_rate` = `_get_conversion_rate(C, A_linked)` — cada linked tiene el suyo
- `counterpart_currency_amount` = `amount × counterpart_rate` — monto del linked en B

---

## Cambios detallados

### 1. Eliminar restricción de diarios para linked payments

```python
# Antes (account_payment.py, _compute_available_journal_ids):
if rec.main_payment_id:
    journals = journals.filtered(
        lambda j: j._origin.id != bundle_journal_id and not j.currency_id
    )

# Después:
if rec.main_payment_id:
    journals = journals.filtered(
        lambda j: j._origin.id != bundle_journal_id
    )
```

Solo se excluye el diario bundle; se permiten todos los demás, con o sin moneda.

### 2. No propagar `counterpart_rate` como default

```xml
<!-- Antes (context de link_payment_ids en vista XML): -->
'default_counterpart_exchange_rate': counterpart_exchange_rate,

<!-- Después: ELIMINAR esta línea -->
<!-- counterpart_rate se computa automáticamente por _compute_counterpart_rate
     en payment_pro, basándose en currency_id (A del linked) y
     counterpart_currency_id (B, heredado del main). -->
```

**Justificación:** Si propagamos un default, el rate del main (A_main→B) se aplica al
linked que puede tener una A diferente. Al no propagar, `_compute_counterpart_rate`
calcula el rate correcto para cada linked según su propio diario.

**Se mantiene la propagación de:**
- `default_counterpart_currency_id`: B del main → cada linked hereda B
- `default_company_id`, `default_partner_id`, `default_payment_type`, etc.

### 3. Eliminar `counterpart_exchange_rate = fields.Float(recursive=True)`

```python
# Eliminar esta línea:
counterpart_exchange_rate = fields.Float(recursive=True)

# Y el bloque comentado:
# @api.depends("main_payment_id.counterpart_exchange_rate")
# def _compute_counterpart_exchange_rate(self):
#     ...
```

Ya no es necesario. `counterpart_rate` se computa en `account_payment_pro` para cada
pago independientemente.

### 4. `bundle_counterpart_currency_amount` — cambiar currency_field

```python
# Antes:
bundle_counterpart_currency_amount = fields.Monetary(
    currency_field="counterpart_currency_id",
    compute="_compute_bundle_counterpart_currency_amount",
)

# Después:
bundle_counterpart_currency_amount = fields.Monetary(
    currency_field="destination_currency_id",
    compute="_compute_bundle_counterpart_currency_amount",
)
```

El compute no cambia — ya suma `counterpart_currency_amount` que está en B.

### 5. `_compute_counterpart_currency_amount` — simplificar para main_payment

```python
@api.depends()
def _compute_counterpart_currency_amount(self):
    main_payment_ids = self.filtered("is_main_payment")
    super(AccountPayment, self - main_payment_ids)._compute_counterpart_currency_amount()
    for rec in main_payment_ids:
        # El main_payment tiene amount=0. Su counterpart_currency_amount
        # representa lo que cancela por retenciones + write-off.
        # withholdings_amount y write_off_amount ya están en B (destination_currency_id).
        # counterpart_currency_amount también está en B. No hay conversión.
        rec.counterpart_currency_amount = rec.withholdings_amount + rec.write_off_amount
```

**Antes:** Dividía `(withholdings + write_off) / counterpart_exchange_rate` para
convertir de C a B. Tras el refactor los campos ya están en B.

### 6. `_compute_payment_difference` — operar enteramente en B

```python
def _compute_payment_difference(self):
    linked = self.filtered("main_payment_id")
    for rec in linked:
        main = rec.main_payment_id
        # Sumar aportes de todos los linked payments en moneda B.
        # counterpart_currency_amount = amount_A × counterpart_rate = monto en B.
        # Funciona para cualquier A (ARS, USD, EUR) porque cada linked
        # tiene su propio counterpart_rate.
        total_payments_in_b = sum(
            main.link_payment_ids.mapped("counterpart_currency_amount")
        )
        rec.payment_difference = (
            main.selected_debt
            - total_payments_in_b
            - main.withholdings_amount
            - main.write_off_amount
        )
    super(AccountPayment, self - linked)._compute_payment_difference()
```

**Antes:** Usaba `amount_company_currency_signed` (C) y restaba de campos en B.
**Ahora:** Todo en B. `counterpart_currency_amount` de cada linked ya está en B.

### 7. `_onchange_withholdings` — convertir B→A para linked payments

```python
@api.onchange("withholdings_amount")
def _onchange_withholdings(self):
    main_payments = self.filtered("is_main_payment")
    main_payments.amount = 0
    for rec in self.filtered(lambda x: x.main_payment_id):
        # payment_difference está en B, amount está en A.
        # Convertir B→A: dividir por counterpart_rate (= B/A).
        counterpart = rec.counterpart_rate or 1.0
        diff_in_a = rec.payment_difference / counterpart if counterpart else rec.payment_difference
        amount = rec.amount + diff_in_a
        rec.amount = amount if amount > 0 else 0
    super(AccountPayment, self - main_payments)._onchange_withholdings()
```

**Antes:** Sumaba `rec.payment_difference` (B) directamente a `rec.amount` (A) —
incorrecto cuando A ≠ B.

### 8. Fix `_get_bundle_journal` para outbound

```python
# Antes (res_company.py) — bug: outbound usa inbound_payment_method_line_ids:
@tools.ormcache("payment_type")
def _get_bundle_journal(self, payment_type: str) -> int:
    if payment_type == "inbound":
        return self.env["account.journal"].search([
            ("inbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
            ("company_id", "=", self.id),
        ]).id
    else:
        return self.env["account.journal"].search([
            ("inbound_payment_method_line_ids...",  # ← BUG: debería ser outbound
            ...

# Después:
@tools.ormcache("payment_type")
def _get_bundle_journal(self, payment_type: str) -> int:
    field = (
        "inbound_payment_method_line_ids"
        if payment_type == "inbound"
        else "outbound_payment_method_line_ids"
    )
    return self.env["account.journal"].search([
        (f"{field}.payment_method_id.code", "=", "payment_bundle"),
        ("company_id", "=", self.id),
    ], limit=1).id
```

### 9. Vista XML — actualizar context de `link_payment_ids`

```xml
<!-- Antes: -->
<field name="link_payment_ids"
    context="{
        ...
        'default_counterpart_currency_id': counterpart_currency_id,
        'default_counterpart_exchange_rate': counterpart_exchange_rate,
        ...
    }" .../>

<!-- Después: -->
<field name="link_payment_ids"
    context="{
        ...
        'default_counterpart_currency_id': counterpart_currency_id,
        ...
    }" .../>
```

Se elimina `default_counterpart_exchange_rate` (renombrado y ya no se propaga).

### 10. Vista XML — list view de linked payments

```xml
<!-- Antes: -->
<field name="counterpart_exchange_rate" string="Rate" optional="hide"/>

<!-- Después: -->
<field name="user_counterpart_rate" string="Rate" optional="hide"/>
```

`user_counterpart_rate` es el UX helper que muestra el rate en dirección legible.

### 11. Vista XML — visibilidad de campos counterpart en linked form

```xml
<!-- Antes: -->
<xpath expr="//label[@for='counterpart_currency_amount']" position="attributes">
    <attribute name="invisible">not counterpart_currency_id</attribute>
</xpath>

<!-- Después (consistente con payment_pro): -->
<xpath expr="//label[@for='counterpart_currency_amount']" position="attributes">
    <attribute name="invisible">currency_id == counterpart_currency_id</attribute>
</xpath>
```

Mostrar el monto en moneda de contrapartida solo cuando A ≠ B (no cuando B está vacío,
que ya no ocurre — `counterpart_currency_id` siempre tiene valor).

Misma lógica para los otros divs/fields de counterpart en la vista de linked.

### 12. Report template — corregir monedas de display

```xml
<!-- Antes: payment_total con display_currency = company_currency_id (C) -->
<span t-out="o.payment_total"
    t-options="{'widget': 'monetary', 'display_currency': o.company_currency_id}"/>

<!-- Después: payment_total está en B (destination_currency_id) -->
<span t-out="o.payment_total"
    t-options="{'widget': 'monetary', 'display_currency': o.destination_currency_id}"/>
```

Misma corrección para `matched_amount + unmatched_amount` en el matching_table footer.

---

## Ejemplo: bundle multimoneda

**Escenario:** Factura 1.000 USD. Compañía argentina (C=ARS).
Pago con bundle: 500 USD en efectivo + 600.000 ARS en transferencia + retención IIBB.

| Pago | A (diario) | B (cancelación) | amount (A) | counterpart_rate (A→B) | counterpart_currency_amount (B) |
|------|-----------|----------------|-----------|----------------------|-------------------------------|
| Main | ARS (bundle) | USD | 0 | — | = withholdings_amount (B) |
| Linked 1 | USD | USD | 500 | 1.0 | 500 USD |
| Linked 2 | ARS | USD | 600.000 | 0.000833 | 500 USD |

```
selected_debt       = 1.000 USD
total_linked_in_b   = 500 + 500 = 1.000 USD
withholdings_amount = 30 USD (≈ 36.000 ARS en C)
write_off_amount    = 0
payment_difference  = 1.000 - 1.000 - 30 - 0 = -30 USD
→ _onchange_withholdings ajusta Linked 2:
  diff_in_a = -30 / 0.000833 = -36.000 ARS
  Linked 2 amount = 600.000 + (-36.000) = 564.000 ARS
  Linked 2 counterpart_currency_amount = 564.000 × 0.000833 ≈ 470 USD
→ payment_difference recalcula: 1.000 - (500 + 470) - 30 = 0 ✓
```

---

## Resumen de archivos a modificar

### `models/account_payment.py`

| Cambio | Tipo |
|--------|------|
| Eliminar `counterpart_exchange_rate = fields.Float(recursive=True)` | Breaking |
| `bundle_counterpart_currency_amount` currency_field → `destination_currency_id` | Fix |
| `_compute_counterpart_currency_amount` → simplificar para main_payment | Rewrite |
| Eliminar bloque comentado `_compute_counterpart_exchange_rate` | Cleanup |
| `_compute_payment_difference` → operar en B con `counterpart_currency_amount` | Rewrite |
| `_onchange_withholdings` → convertir B→A para linked payments | Fix |
| `_compute_available_journal_ids` → eliminar `not j.currency_id` | Feature |

### `models/res_company.py`

| Cambio | Tipo |
|--------|------|
| `_get_bundle_journal` → fix outbound (usa `inbound_` en ambos casos) | Bugfix |

### `views/account_payment_view.xml`

| Cambio | Tipo |
|--------|------|
| Context: eliminar `default_counterpart_exchange_rate` | Breaking |
| List view: `counterpart_exchange_rate` → `user_counterpart_rate` | Rename |
| Linked form: `invisible` de counterpart → `currency_id == counterpart_currency_id` | Fix |

### `views/report_payment_receipt_templates.xml`

| Cambio | Tipo |
|--------|------|
| `display_currency` de totals → `destination_currency_id` (no `company_currency_id`) | Fix |

---

## Criterios de aceptación

- [ ] El módulo instala sin errores tras los refactors de payment_pro y l10n_ar_tax
- [ ] No hay referencias a `counterpart_exchange_rate` en el código
- [ ] No hay referencias a `amount_company_currency_signed_pro` ni `exchange_rate`
- [ ] Linked payments pueden usar diarios en cualquier moneda (ARS, USD, EUR)
- [ ] `counterpart_currency_id` de linked payments viene del main y es readonly
- [ ] Cada linked payment computa su propio `counterpart_rate` según su diario
- [ ] `_compute_payment_difference` opera enteramente en moneda B
- [ ] `_compute_counterpart_currency_amount` para main_payment no hace conversión
- [ ] `_onchange_withholdings` convierte payment_difference (B) a moneda del diario (A)
- [ ] Bundle ARS puro funciona (caso base, regresión)
- [ ] Bundle USD puro (A=B=USD, C=ARS) funciona
- [ ] Bundle mixto (linked en ARS + linked en USD pagando deuda USD) funciona
- [ ] Los montos en list view y report se muestran en la moneda correcta
- [ ] `_get_bundle_journal` funciona para outbound

---

## Casos de test

### B.1 — Bundle local (A=B=C=ARS)

Factura 10.000 ARS. Bundle: linked 4.500 ARS + linked 4.500 ARS + retención 1.000 ARS.
- `selected_debt` = 10.000 ARS
- `total_linked_in_b` = 4.500 + 4.500 = 9.000 ARS
- `withholdings_amount` = 1.000 ARS
- `payment_difference` = 10.000 - 9.000 - 1.000 = 0 ✓

### B.2 — Bundle divisa pura (A=B=USD, C=ARS)

Factura 1.000 USD. Bundle: linked 970 USD + retención ≈ 30 USD.
- Todos los rates = 1.0 (A=B) excepto accounting_rate (para C)
- `counterpart_currency_amount` de linked = 970 USD
- `withholdings_amount` = 30 USD (≈ 36.000 ARS stored)
- `payment_difference` = 1.000 - 970 - 30 = 0 ✓

### B.3 — Bundle mixto: linked ARS + linked USD pagando deuda USD

Factura 1.000 USD. Bundle: linked 500 USD + linked 600.000 ARS + retención.
- Linked 1: A=USD, B=USD, `counterpart_rate`=1.0, `counterpart_currency_amount`=500 USD
- Linked 2: A=ARS, B=USD, `counterpart_rate`≈0.000833, `counterpart_currency_amount`≈500 USD
- `payment_difference` = 1.000 - (500+500) - withholdings = ...
- Verificar que `_onchange_withholdings` ajusta el amount de linked 2 en ARS, no en USD

### B.4 — Bundle ARS pagando deuda USD (A=C=ARS, B=USD)

Factura 100 USD. Bundle: linked 150.000 ARS (counterpart_rate da ~125 USD).
Retención = 1.500 ARS (≈ 1 USD en B).
- Linked: A=ARS, B=USD, `counterpart_currency_amount` = 150.000 × 0.000833 ≈ 125 USD
- `selected_debt` = 100 USD
- `withholdings_amount` ≈ 1 USD
- `payment_difference` = 100 - 125 - 1 = -26 USD → hay excedente, normal
- Verificar que el report muestra totals en USD (B), no en ARS (C)

---

## Impacto en otros módulos

| Módulo | Tipo | Acción |
|--------|------|--------|
| `account_payment_pro` | Dependencia upstream (T-62550) | Debe estar completo antes |
| `l10n_ar_tax` | Dependencia upstream (retenciones) | Debe estar completo antes |
| `account_payment_pro_receiptbook` | Dependencia | Verificar que no tenga referencias a campos eliminados |
