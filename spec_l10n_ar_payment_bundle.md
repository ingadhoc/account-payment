# Spec: l10n_ar_payment_bundle — Adaptación al modelo tri-monetario

**Módulo:** `l10n_ar_payment_bundle` (ADHOC)
**Depende de:** `account_payment_pro` refactor (T-62550) + `l10n_ar_tax` refactor
**Issue:** T-XXXXX
**Autor:** Juan
**Fecha:** 2025-03-18 (rev. final)
**Estado:** Aprobado

---

## Contexto

El módulo `l10n_ar_payment_bundle` permite crear "recibos bundle": un pago principal
(`is_main_payment=True`, amount=0) que agrupa pagos vinculados (`link_payment_ids`)
de distintos diarios/métodos. El pago principal concentra la deuda, retenciones y
write-off; los pagos vinculados son los medios de pago reales.

El refactor de `account_payment_pro` introduce cambios que rompen este módulo:
- Campos renombrados: `counterpart_exchange_rate` → `counterpart_rate`
- Campos eliminados: `amount_company_currency_signed_pro`, `exchange_rate`
- Campos con moneda cambiada: `payment_total`, `selected_debt`, `withholdings_amount`,
  `write_off_amount`, `payment_difference` pasan de `company_currency_id` a `destination_currency_id`
- `counterpart_currency_amount` pasa de `counterpart_currency_id` a `destination_currency_id`

---

## Alcance

**Entra:**
- Adaptar todas las referencias a campos renombrados/eliminados
- Reescribir `_compute_counterpart_currency_amount` para main_payment
- Reescribir `_compute_payment_difference` para linked payments
- Adaptar `bundle_counterpart_currency_amount` al nuevo currency_field
- Adaptar vistas (XML) a campos renombrados
- Limpiar código comentado obsoleto

**No entra:**
- Cambios funcionales nuevos (solo adaptación al nuevo modelo)

---

## Mapa de cambios por breaking change

### 1. `counterpart_exchange_rate` → `counterpart_rate`

| Ubicación | Cambio |
|-----------|--------|
| Línea 13: `counterpart_exchange_rate = fields.Float(recursive=True)` | Renombrar a `counterpart_rate` |
| Línea 68-71: `_compute_counterpart_currency_amount` usa `rec.counterpart_exchange_rate` | Ver punto 3 abajo |
| Líneas 108-113: bloque comentado `_compute_counterpart_exchange_rate` | Eliminar (dead code) |
| Vista XML línea 136: contexto `default_counterpart_exchange_rate` | Renombrar a `default_counterpart_rate` |
| Vista XML línea 204: `counterpart_exchange_rate` en list view | Cambiar a `user_counterpart_rate` (UX helper) |

### 2. `bundle_counterpart_currency_amount` — currency_field

```python
# Antes:
bundle_counterpart_currency_amount = fields.Monetary(
    currency_field="counterpart_currency_id",
    ...
)
# Después:
bundle_counterpart_currency_amount = fields.Monetary(
    currency_field="destination_currency_id",
    ...
)
```

### 3. `_compute_counterpart_currency_amount` — reescribir para main_payment

El código actual para main_payment:
```python
rec.counterpart_currency_amount = (
    rec.withholdings_amount + rec.write_off_amount
) / rec.counterpart_exchange_rate
```

El pago principal tiene amount=0, su `counterpart_currency_amount` representa cuánta
deuda cancela por retenciones y write-off. Ahora `withholdings_amount` y `write_off_amount`
ya están en B (`destination_currency_id`), así que no necesitan conversión:

```python
@api.depends()
def _compute_counterpart_currency_amount(self):
    main_payment_ids = self.filtered("is_main_payment")
    super(AccountPayment, self - main_payment_ids)._compute_counterpart_currency_amount()
    for rec in main_payment_ids:
        # withholdings_amount y write_off_amount ya están en B (destination_currency_id)
        # counterpart_currency_amount también está en B, no hay conversión
        rec.counterpart_currency_amount = rec.withholdings_amount + rec.write_off_amount
```

### 4. `_compute_payment_difference` — reescribir para linked payments

El código actual mezcla monedas incorrectamente después del refactor:
```python
# Usa amount_company_currency_signed (C) pero selected_debt, withholdings_amount,
# write_off_amount ahora están en B
amount_payments = abs(amount_inbound + amount_outbound)  # en C
rec.payment_difference = rec.main_payment_id.selected_debt - amount_payments - ...  # B - C = ¡error!
```

Necesita operar enteramente en B. Los importes de los linked payments deben convertirse
a B usando `counterpart_currency_amount` (que ya está en B):

```python
def _compute_payment_difference(self):
    linked = self.filtered("main_payment_id")
    for rec in linked:
        main = rec.main_payment_id
        # Total pagado por linked payments en moneda B
        # counterpart_currency_amount ya está en destination_currency_id (B)
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

**Nota:** Si A=B para todos los linked payments (caso frecuente sin divisa),
`counterpart_currency_amount = amount`, así que el cálculo es equivalente al actual.
Cuando A!=B, usar `counterpart_currency_amount` es correcto porque expresa el pago
en moneda de deuda.

**Alternativa si `counterpart_currency_amount` no está disponible durante el draft:**
Los linked payments en draft podrían no tener `counterpart_currency_amount` computado.
Evaluar si conviene usar `amount * counterpart_rate` como fallback, o si el compute
chain ya lo resuelve.

### 5. `_compute_payment_total` — sin cambios funcionales

```python
@api.depends("link_payment_ids")
def _compute_payment_total(self):
    super()._compute_payment_total()
    for rec in self:
        rec.payment_total += sum(rec.link_payment_ids.mapped("payment_total"))
```

`payment_total` ahora está en B tanto en el main como en los linked. La suma es
correcta si todos comparten la misma `destination_currency_id`. El constraint
existente ya asegura misma company — verificar que los linked payments hereden
el mismo `counterpart_currency_id` del main (lo hace `_onchange_counterpart_currency_id`).

### 6. `_compute_matched_amounts` — revisar

El código actual:
```python
rec.matched_amount += sum(linked_payments.mapped("matched_amount"))
rec.unmatched_amount = abs(rec.payment_total) - rec.matched_amount
```

`matched_amount` ahora está en B. Si todos los linked y el main tienen la misma
`destination_currency_id`, la suma es correcta. Sin cambios funcionales necesarios,
pero verificar en testing.

### 7. Vista XML `view_account_payment_custom_list` — actualizar

```xml
<!-- Antes -->
<field name="amount_company_currency_signed" widget="monetary" string="Amount" sum="Total"/>
<field name="counterpart_exchange_rate" string="Rate" optional="hide"/>
<field name="counterpart_currency_amount" string="Amount in SC" optional="hide" sum="Total" widget="monetary"/>

<!-- Después -->
<field name="amount_company_currency_signed" widget="monetary" string="Amount" sum="Total"/>
<field name="user_counterpart_rate" string="Rate" optional="hide"/>
<field name="counterpart_currency_amount" string="Amount in SC" optional="hide" sum="Total" widget="monetary"/>
```

Nota: `amount_company_currency_signed` es campo de Odoo base (no el `_pro` eliminado),
se mantiene.

### 8. Vista XML contexto de `link_payment_ids` — actualizar

```xml
<!-- Antes -->
'default_counterpart_exchange_rate': counterpart_exchange_rate,

<!-- Después -->
'default_counterpart_rate': counterpart_rate,
```

### 9. Vista XML — referencias a counterpart

```xml
<!-- Antes (línea 62-65) en view_account_payment_from_bundle_form -->
<field name="counterpart_currency_id" position="attributes">
    <attribute name="readonly">1</attribute>
    <attribute name="force_save">1</attribute>
</field>

<!-- Mantener sin cambios — counterpart_currency_id sigue existiendo -->
```

Las referencias a `counterpart_currency_amount` en la vista (líneas 68-76) con
`invisible="not counterpart_currency_id"` pueden cambiar a
`invisible="currency_id == counterpart_currency_id"` para ser consistentes con
la nueva lógica (solo mostrar cuando A != B1), pero no es estrictamente breaking.

### 10. Limpiar dead code

Eliminar el bloque comentado (líneas 108-113):
```python
# @api.depends("main_payment_id.counterpart_exchange_rate")
# def _compute_counterpart_exchange_rate(self):
#     ...
```

---

## Resumen de archivos a modificar

### `models/account_payment.py`

| Línea(s) | Cambio | Tipo |
|----------|--------|------|
| 13 | `counterpart_exchange_rate` → `counterpart_rate` (recursive field) | Rename |
| 14-16 | `bundle_counterpart_currency_amount` currency_field → `destination_currency_id` | Fix |
| 63-73 | `_compute_counterpart_currency_amount` → simplificar para main_payment | Rewrite |
| 108-113 | Eliminar bloque comentado | Cleanup |
| 315-334 | `_compute_payment_difference` → operar en B | Rewrite |

### `views/account_payment_view.xml`

| Línea(s) | Cambio | Tipo |
|----------|--------|------|
| 136 | `default_counterpart_exchange_rate` → `default_counterpart_rate` | Rename |
| 203 | `amount_company_currency_signed` → mantener (es campo Odoo base) | Verificar |
| 204 | `counterpart_exchange_rate` → `user_counterpart_rate` | Rename |

---

## Criterios de aceptación

- [ ] El módulo instala y carga sin errores tras el refactor de payment_pro y l10n_ar_tax
- [ ] No hay referencias a `counterpart_exchange_rate` (renombrado a `counterpart_rate`)
- [ ] No hay referencias a `amount_company_currency_signed_pro` ni `exchange_rate`
- [ ] `_compute_payment_difference` opera enteramente en moneda B
- [ ] `_compute_counterpart_currency_amount` para main_payment no divide por rate (ya está en B)
- [ ] Bundle con pagos en ARS puro funciona (caso base, regresión)
- [ ] Bundle con pagos en USD (A=B=USD, C=ARS) funciona
- [ ] Bundle con pagos mixtos (linked en ARS pagando deuda USD) funciona
- [ ] Los montos en la list view de linked payments se muestran correctamente

---

## Casos de test sugeridos

### B.1 — Bundle local (A=B=C=ARS)

Pago de factura 10.000 ARS con bundle de dos pagos de 4.500 ARS + retención 1.000 ARS.
Verificar payment_total, payment_difference, matched_amounts.

### B.2 — Bundle divisa (A=B=USD, C=ARS)

Factura 1.000 USD. Bundle con un linked payment de 970 USD + retención 30 USD (en B=USD).
Verificar que counterpart_currency_amount y payment_total sumen correctamente en USD.

### B.3 — Bundle con linked en ARS pagando deuda USD (A=C=ARS, B=USD)

Factura 100 USD. Bundle con linked payment de 145.000 ARS (counterpart_rate da ~100 USD).
Retención 1.500 ARS (= 1 USD en B). Verificar payment_difference en USD.

---

## Impacto en otros módulos

| Módulo | Tipo | Acción |
|--------|------|--------|
| `account_payment_pro` | Dependencia upstream (T-62550) | Debe estar completo antes |
| `l10n_ar_tax` | Dependencia upstream (retenciones) | Debe estar completo antes |
| `account_payment_pro_receiptbook` | Dependencia | Verificar que no tenga referencias a campos eliminados |
