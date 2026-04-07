# SPEC DE MIGRACIÓN — account_payment_pro 19.0.2.0.0

## Estrategia de scripts

- **Pre-migrate**: solo backup de columnas originales (`x_bkp_*`), creación de columnas
  nuevas con defaults seguros para que el ORM no encole recomputes masivos, y marcado
  de todas las filas existentes con un sentinel `x_bkp_migrated = TRUE`.
- **Post-migrate**: toda la lógica de transformación de valores. Cada UPDATE filtra por
  `x_bkp_migrated = TRUE` para que **pagos creados después de la migración nunca sean
  tocados**, incluso si el post se re-ejecuta. Lectura siempre desde `x_bkp_*` (inmutables).
- **Motivo**: facilita auditoría, re-ejecución ante bugs, y aísla los pagos nuevos.

---

## 1. counterpart_currency_id

Solo se seteaba en algunos casos. Ahora es requerido para todos los pagos.

Casos históricos:

a) **Estaba definida, distinta a currency_id, y currency_id = company_currency_id** → caso
   normal (pago en ARS, counterpart en USD). El rate estaba bien almacenado. Se conserva.

b) **Estaba definida, distinta a currency_id, pero currency_id ≠ company_currency_id** →
   en el código viejo `_use_counterpart_currency()` requería `currency_id == company_currency_id`,
   por lo que a nivel asiento se ignoraba la counterpart. **Migración**: alinear el dato
   → `counterpart_currency_id = currency_id`, `counterpart_rate = 1.0`.

c) **No estaba definida** (la mayoría) → la moneda real de contrapartida era la moneda del
   diario (si estaba definida) o la de la compañía. Se pobla según lógica del nuevo compute
   en 4 sub-pasos: transferencias internas, cuenta con moneda forzada, to_pay_lines con moneda
   única (sin reconcile), fallback a moneda de compañía.

d) **Transferencias internas** → nunca se definía (False, rate 0/NULL). En la nueva versión
   se usa para representar la moneda del diario de destino.

**✅ Decisión: Opción 1.1** — computar para TODOS los pagos.
Es `store=True` y otros campos dependen de él; dejarlo NULL rompe cómputos dependientes.

> **Alternativa descartada (1.2)**: no computar para pagos históricos, no hacerla requerida
> por vista salvo en draft. No viable porque campos como `counterpart_currency_amount`,
> `payment_total`, `selected_debt`, etc. dependen de ella.

---

## 2. counterpart_rate

Antes se llamaba `counterpart_exchange_rate`. Cambio de nombre y semántica:

- **Viejo**: formato user-friendly C/B1 (ej: 1428 = cuántos ARS por 1 USD)
- **Nuevo**: formato Odoo nativo B1/A (ej: 0.000700 = USD/ARS)
- **Conversión**: `counterpart_rate = 1 / counterpart_exchange_rate`

Para pagos del caso (b) (A ≠ C con counterpart ignorada): `counterpart_rate = 1.0`.
Para pagos que no tenían `counterpart_exchange_rate` (NULL/0): se computa el rate según
la `counterpart_currency_id` recién poblada y `res_currency_rate`.

---

## 3. counterpart_currency_amount

No era almacenado (compute sin `store=True`). Ahora es `store=True`.
Fórmula: `amount × counterpart_rate` cuando A ≠ B1, `amount` cuando A = B1.
Siempre positivo (se fuerza ABS).

---

## 4. accounting_rate y force_amount_company_currency

`accounting_rate` es campo nuevo (`store=True`). Reemplaza la combinación
`force_amount_company_currency` + `amount_company_currency` (compute sin store) + `exchange_rate`.

- `accounting_rate` = A/C en formato Odoo nativo (ej: 0.000667 para USD cuando C=ARS).

4.a) Si existe `force_amount_company_currency` (monto forzado en C):
     `accounting_rate = amount / force_amount_company_currency` (= A/C).

4.b) Si no existe (se usaba rate del sistema on-the-fly):

**✅ Decisión: Opción 4.b.2** — computar desde el histórico de monedas (`res_currency_rate`).

> **Alternativas descartadas**:
> - **4.b.1**: no mostrar ni computar. No viable porque el campo es `store=True` y se usa
>   para cerrar el asiento contable.
> - **4.b.3**: calcular desde los apuntes contables (`balance / amount_currency` de la
>   liquidity line). Más preciso pero mucho más complejo. Viable como fallback futuro si
>   se detectan discrepancias en los rates históricos.

---

## 5. write_off_amount

Cambio de moneda de referencia: `company_currency_id` → `destination_currency_id`.

Factor de conversión: `counterpart_rate × accounting_rate` = (B1/A) × (A/C) = B1/C.

- Cuando `reconcile_on_company_currency = True`: `destination = C` → factor forzado a 1.0.
- Cuando B1 = C (lo más habitual) el factor se auto-neutraliza a 1.0 igualmente.

No hay cambio de signo.

---

## 6. unreconciled_amount

Dos ajustes simultáneos:

1. **Cambio de moneda**: `company_currency_id` → `destination_currency_id`. Mismo factor
   que `write_off_amount` (con la misma lógica de `reconcile_on_company_currency`).

2. **Cambio de signo**: la lógica de `selected_debt` cambió de usar `partner_type` a
   `payment_type`. Se invierte el signo para las combinaciones invertidas:
   `customer + outbound` y `supplier + inbound`.

---

## Resumen de pasos del post-migrate

Todos los pasos filtran por `x_bkp_migrated = TRUE` (sentinel del pre-migrate).

| Paso | Campo | Acción |
|------|-------|--------|
| 1a | `accounting_rate` | A == C → 1.0 |
| 1b | `accounting_rate` | A ≠ C con force → `amount / x_bkp_force` |
| 1c | `accounting_rate` | A ≠ C sin force → tasa histórica de `res_currency_rate` |
| 2 | `counterpart_rate` | Restaurar `1 / x_bkp_counterpart_exchange_rate` (caso a) |
| 3 | `counterpart_currency_id` + `counterpart_rate` | Fix caso (b): A≠C con counterpart definida → B1=A, rate=1 |
| 4.1–4.4 | `counterpart_currency_id` | Poblar NULLs según lógica del compute |
| 5b | `counterpart_rate` | B1 = C recién poblado → `1/accounting_rate` |
| 5c | `counterpart_rate` | B1 ≠ A ≠ C recién poblado → desde `res_currency_rate` |
| 6 | `write_off_amount` | Convertir C → destination (factor `counterpart_rate × accounting_rate`) |
| 7 | `unreconciled_amount` | Convertir C → destination + fix signo |
| 8 | `counterpart_currency_amount` | Poblar `amount × counterpart_rate`, asegurar ≥ 0 |
| 9 | — | Validación: check NULLs en posted payments migrados |

## Limitaciones conocidas

- **`counterpart_currency_amount` con valor manual previo**: en el código viejo era
  `compute` sin `store=True`, por lo que **no existía columna en DB**. Si un pago tenía
  un valor "forzado" via inverse en sesión, ese valor no se preservó (se recomputa con
  `amount × counterpart_rate`). No hay backup posible.
- **`accounting_rate` sin force**: se computa desde `res_currency_rate` a la fecha del
  pago (4.b.2). Si las cotizaciones históricas fueron modificadas después del pago, el
  rate migrado puede diferir del que efectivamente se usó al postear el asiento.
