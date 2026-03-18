# Decisions — account_payment_pro refactor (T-62550)

## ADR-001 — Modelo tri-monetario en lugar de pivotar sobre company_currency
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** El módulo actual usa `company_currency_id` como pivote de casi toda la UX,
lo que hace imposible trabajar correctamente con pagos bimonetarios.

**Decisión:** Introducir tres monedas explícitas: A (liquidez), B1/B2 (deuda/UX), C (contable).

**Consecuencias:** Refactor significativo. Los campos que usaban `company_currency_id`
como `currency_field` migran a `destination_currency_id`.

---

## ADR-002 — `destination_currency_id` no se almacena
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** Es tentador almacenarlo para performance.

**Decisión:** No almacenado. Es un campo derivado de `counterpart_currency_id` y
`reconcile_on_company_currency`. Almacenarlo crearía inconsistencias ante cambios
en la cuenta contable o en las líneas de deuda.

---

## ADR-003 — B1 editable solo en casos específicos, no siempre
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** Se evaluó hacerlo siempre editable para mayor flexibilidad.

**Decisión:** Solo editable cuando la cuenta no tiene moneda definida (o es igual a la
de la compañía) Y (no hay reconcile O no hay deuda seleccionada). Si la cuenta tiene
moneda definida (distinta a la de la compañía), el campo es informativo; si hay deuda
seleccionada sin reconcile, la moneda la dictan las líneas.

---

## ADR-004 — Deprecar `force_amount_company_currency`, reemplazar con `accounting_rate`
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** `force_amount_company_currency` era un boolean + monto acoplado.

**Decisión:** Separar en `accounting_rate` (Float, tasa A→C en formato Odoo nativo).
Es más explícito, consistente con como Odoo maneja otras tasas, y permite edición
directa de la tasa.

---

## ADR-005 — Lógica de retenciones NO entra en este refactor
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** `l10n_ar_tax` depende de varios campos que cambian su moneda de referencia.

**Decisión:** Este refactor solo migra la moneda de los campos existentes de retenciones
a `destination_currency_id`. La lógica de cálculo de retenciones se especifica en un
anexo separado para `l10n_ar_tax`.

**Riesgo:** Hay que validar cuidadosamente que el cambio de moneda en
`withholdable_advanced_amount` y `withholdings_amount` no rompa los cálculos existentes.

**Riesgo adicional:** `l10n_ar_tax._prepare_move_withholding_lines` usa
`self.exchange_rate or 1.0` para calcular `amount_currency`. Con el renombre a
`accounting_rate` y el cambio de formato (user-friendly → Odoo nativo), esa fórmula
produce resultados incorrectos. La adaptación se hace en la iteración de retenciones.

---

## ADR-006 — Validación de moneda única en deuda seleccionada via Python constraint
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** Sin reconcile, si el usuario selecciona deudas de distintas monedas,
`counterpart_currency_id` no puede resolverse de forma determinística.

**Decisión:** `@api.constrains` en Python. No raise desde el computed (side effect,
Odoo lo puede llamar en contextos donde un error rompe cosas inesperadamente).
No SQL constraint (la condición depende de `reconcile_on_company_currency`).

```python
@api.constrains("to_pay_move_line_ids", "counterpart_currency_id")
def _check_to_pay_lines_currency(self):
    for rec in self:
        if rec.reconcile_on_company_currency:
            continue
        currencies = rec.to_pay_move_line_ids.mapped("currency_id")
        if len(currencies) > 1:
            raise ValidationError(
                _("All selected debt lines must have the same currency. "
                  "Found: %s") % ", ".join(currencies.mapped("name"))
            )
```

---

## ADR-007 — Rates almacenados en formato Odoo, UX helpers no almacenados por campo
**Fecha:** 2025-03-17 | **Estado:** Aceptado

**Contexto:** Odoo guarda tasas en formato "unidades de moneda débil por 1 de la fuerte"
invertido (ej: `0.000667` ARS/USD). Los usuarios argentinos esperan ver `1 USD = 1500 ARS`.
Se evaluó un mixin compartido y también cambiar el formato de almacenamiento.

**Decisión:** Mantener el formato interno de Odoo en los campos almacenados
(`accounting_rate`, `counterpart_rate`). Agregar dos campos auxiliares no
almacenados con compute + inverse (`user_accounting_rate`, `user_counterpart_rate`)
directamente en el modelo, sin mixin.

- `user_accounting_rate`: siempre invierte (A es siempre la débil respecto a C en AR).
- `user_counterpart_rate`: inversión condicional según si el rate almacenado es `< 1.0`
  (estricto, no `<= 1.0`). Cuando `rate == 1.0` exacto (paridad 1:1 o misma moneda),
  se muestra directo sin inversión.

**Por qué sin mixin:** Con solo dos campos concretos, un mixin agrega indirección sin
beneficio real. Si en el futuro hay más casos (ej. `account_ux` adopta el mismo approach),
se extrae entonces.

**Pendiente:** Alinear `account_ux` para que `user_invoice_currency_rate` use el mismo
criterio de inversión condicional. Hoy invierte siempre.

---

## ADR-008 — `counterpart_rate` almacena en formato Odoo nativo (invertir datos existentes)
**Fecha:** 2025-03-18 | **Estado:** Aceptado

**Contexto:** `counterpart_exchange_rate` almacenaba en formato user-friendly (ej: 1500).
Al renombrarlo a `counterpart_rate` se unifica con el formato nativo de Odoo (ej: 0.000667).

**Decisión:** Migration script invierte todos los valores stored existentes con
`SET counterpart_rate = 1.0 / counterpart_rate`. El renombre de columna via
`openupgrade.rename_columns` evita drop/recreate.

**Consecuencias:** Los campos UX helpers muestran el inverso, alineado con `accounting_rate`.
Cualquier código externo que lea `counterpart_exchange_rate` directamente necesita adaptarse.

---

## ADR-009 — Migration scripts previenen recomputo masivo de campos stored nuevos
**Fecha:** 2025-03-18 | **Estado:** Aceptado

**Contexto:** Odoo encola recomputo para registros donde un campo stored tiene valor NULL.
En una base con miles de pagos, recomputar todo el historial en el momento de actualización
es inaceptable.

**Decisión:** `pre_migrate.py` puebla via SQL todas las columnas nuevas o renombradas
**antes** de que el ORM cargue la nueva lógica del módulo. Si la columna ya tiene datos,
Odoo no encola nada. `post_migrate.py` verifica que no queden NULLs en pagos posted.

**Aplica a:** `counterpart_rate` (rename + invert), `accounting_rate` (nueva columna,
calculada desde `amount` y `amount_company_currency`).

---

## ADR-010 — `write_off_amount` migra a `destination_currency_id`
**Fecha:** 2025-03-18 | **Estado:** Aceptado

**Contexto:** `write_off_amount` estaba en `company_currency_id`. Al migrar todos los
campos de UX del pago a `destination_currency_id`, `write_off_amount` debe acompañar
el cambio para que la experiencia sea consistente.

**Decisión:** Migrar `write_off_amount` a `destination_currency_id`. El migration script
hace backup de la columna original y convierte los valores usando `counterpart_rate`.

**Consecuencias:** Los pagos existentes con write-off tendrán sus montos re-expresados
en moneda B. Cualquier reporte o lógica que lea `write_off_amount` asumiendo moneda C
necesita adaptarse.
