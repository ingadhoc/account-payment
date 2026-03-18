# Spec: Refactor account_payment_pro — Modelo tri-monetario y soporte bimonetario

**Módulo principal:** `account_payment_pro` (ADHOC)
**Módulos afectados:**
- `account` (Odoo SA — sin modificaciones directas, herencia)
- `account_ux` (ADHOC — provee `reconcile_on_company_currency` en `res.company`, agregar como dependencia)
- `l10n_ar_tax` (ADHOC equipo Contable — campos de retenciones migran a `destination_currency_id`)

**Issue:** T-62550
**Autor:** Juan
**Fecha:** 2025-03-17
**Estado:** Final

---

## Contexto y motivación

El módulo acumula deuda técnica significativa: funcionalidades agregadas iterativamente
generaron un modelo inconsistente que pivota sobre `company_currency_id` para casi toda
la UX, lo cual hace imposible o muy confuso trabajar con pagos bimonetarios.

El refactor apunta a reemplazar ese pivote por un **modelo de tres monedas explícitas**,
clarificar la UX y eliminar campos deprecated que ya no tienen sentido.

---

## Alcance

**Entra:**
- Redefinición del modelo de monedas del pago (A / B1 / B2 / C)
- Nuevos campos calculados `counterpart_currency_id` y `destination_currency_id`
- Renombrar `exchange_rate` (non-stored) → `accounting_rate` (stored, formato Odoo nativo)
- Renombrar `counterpart_exchange_rate` (stored, formato user-friendly) → `counterpart_rate` (stored, formato Odoo nativo) + migration script que invierte los valores
- Agregar `account_ux` como dependencia (provee campo `reconcile_on_company_currency` en `res.company`, que hace que si la cuenta de deuda AR/AP no tiene moneda definida, la conciliación se haga siempre en moneda de la compañía)
- Deprecar y archivar campos legacy (`force_amount_company_currency`, `amount_company_currency`, `amount_company_currency_signed_pro`)
- Migrar `write_off_amount` a `destination_currency_id` (incluye migration de datos)
- Adaptar vista del formulario de pago
- Revisar y adaptar `_prepare_move_lines_per_type` para cubrir todos los casos del modelo tri-monetario
- Adaptar lógica de `payment_matched_amount` en `account.move.line`
- Adaptar `_get_trigger_fields_to_synchronize` y `_create_paired_internal_transfer_payment`
- Migration scripts (ver sección dedicada)
- Tests para los 10 casos de uso documentados

**No entra (scope futuro / anexo separado):**
- Lógica de cálculo de retenciones en `l10n_ar_tax` (será spec aparte). **NOTA:** `l10n_ar_tax._prepare_move_withholding_lines` actualmente usa `self.exchange_rate` que cambia de semántica (formato user-friendly → Odoo nativo). Esa adaptación se hará en la iteración de retenciones.
- Deprecación completa de `reconcile_on_company_currency` (evaluación futura)

---

## Modelo de monedas

El pago pasa de pivotar en `company_currency_id` a un modelo con tres monedas explícitas:

| Símbolo | Campo | Descripción |
|---------|-------|-------------|
| **A** | `currency_id` | Moneda del diario (liquidez: Banco/Caja). Nativo Odoo. |
| **B1** | `counterpart_currency_id` | Moneda del apunte AP/AR. Calculado almacenado, editable condicionalmente. |
| **B2** | `destination_currency_id` | Moneda de UX / conciliación. Calculado NO almacenado. |
| **C** | `company_currency_id` | Moneda contable. Related a `company_id.currency_id`. |

> En la mayoría de los casos B1 = B2 (llamados genéricamente **B**).
> Se diferencian únicamente cuando hay `reconcile_on_company_currency = True`.

---

## Lógica de cálculo de campos clave

### `counterpart_currency_id` (B1) — Calculado, almacenado, editable condicionalmente

```
si destination_account_id.currency_id existe y != company_currency_id:
    → destination_account_id.currency_id
sino:
    si reconcile_on_company_currency:
        → company_currency_id  (editable por usuario)
    sino:
        si to_pay_move_line_ids tiene líneas:
            → moneda de esas líneas  (validar que sean todas la misma moneda)
        sino:
            → company_currency_id  (editable por usuario)
```

**Editable solo cuando:** la cuenta no tiene moneda definida (o es igual a la de la compañía) Y (no hay reconcile O no hay deuda seleccionada).

### `destination_currency_id` (B2) — Calculado, NO almacenado

```
si NO reconcile_on_company_currency:
    → counterpart_currency_id   (B1 = B2)
sino:
    si destination_account_id.currency_id existe y != company_currency_id:
        → destination_account_id.currency_id
    sino:
        → company_currency_id
```

### `accounting_rate` (renombrado desde `exchange_rate`) — Stored, editable

`exchange_rate` era non-stored y computaba `amount_company_currency / amount` (formato user-friendly, ej: 1500).
Al pasarlo a stored, adoptamos **formato Odoo nativo** (ej: `0.000667`), consistente con el resto del sistema.

El migration script puebla `accounting_rate` desde los datos existentes de `amount` y `amount_company_currency`
(ver sección Migration Scripts).

Solo visible si `currency_id != company_currency_id`.

**Campo UX auxiliar `user_accounting_rate` (non-stored):**
Expone el inverso para que el usuario vea y edite `1 USD = 1500 ARS`.

```python
user_accounting_rate = fields.Float(
    compute="_compute_user_accounting_rate",
    inverse="_inverse_user_accounting_rate",
    store=False, digits=0, min_display_digits=2)

@api.depends("accounting_rate")
def _compute_user_accounting_rate(self):
    for rec in self:
        rec.user_accounting_rate = 1.0 / rec.accounting_rate if rec.accounting_rate else 0.0

def _inverse_user_accounting_rate(self):
    for rec in self:
        if rec.user_accounting_rate:
            rec.accounting_rate = 1.0 / rec.user_accounting_rate
```

La vista muestra `user_accounting_rate` con label `1 {currency_id} = X {company_currency_id}`.

### `counterpart_rate` (renombrado desde `counterpart_exchange_rate`) — Stored, editable

`counterpart_exchange_rate` era stored en **formato user-friendly** (ej: 1500 para USD→ARS).
Al renombrarlo a `counterpart_rate` adoptamos **formato Odoo nativo** (ej: `0.000667`).
El migration script invierte todos los valores existentes (ver sección Migration Scripts).

**Cuándo mostrar cada rate:**

Cuando B1 == C (ej: A=USD, B1=ARS, C=ARS), ambos rates representan la misma conversión.
Mostrar los dos es redundante y confuso.

| A | B1 | C | Mostrar |
|---|----|---|---------|
| ARS | ARS | ARS | Ninguno |
| USD | USD | ARS | Solo `accounting_rate` |
| ARS | USD | ARS | Solo `counterpart_rate` |
| USD | ARS | ARS | Solo `accounting_rate` ← B1==C, son el mismo |
| USD | EUR | ARS | Los dos (conversiones distintas) |

Regla: `counterpart_rate` visible solo si `A != B1 AND B1 != C`.

```xml
<!-- Solo visible si A != C -->
<field name="user_accounting_rate"
    invisible="currency_id == company_currency_id"/>

<!-- Solo visible si A != B1 AND B1 != C -->
<field name="user_counterpart_rate"
    invisible="currency_id == counterpart_currency_id
               or counterpart_currency_id == company_currency_id"/>
```

**Sincronización cuando B1 == C:**

Cuando `counterpart_currency_id == company_currency_id`, el compute de
`counterpart_rate` delega en `accounting_rate` para mantenerlos alineados:

```python
@api.depends("accounting_rate", "counterpart_currency_id", "company_currency_id")
def _compute_counterpart_rate(self):
    for rec in self:
        if rec.counterpart_currency_id == rec.company_currency_id:
            rec.counterpart_rate = rec.accounting_rate
        else:
            # lógica normal de cálculo del rate
            ...
```

El inverse de `user_counterpart_rate` también debe propagar a `accounting_rate`
cuando B1 == C.

**Campo UX auxiliar `user_counterpart_rate` (non-stored):**
Se invierte condicionalmente: si el rate almacenado es `< 1.0` (A es la moneda débil),
se muestra invertido. Si `>= 1.0` (A es la fuerte o paridad 1:1), se muestra directo.

**Edge case rate == 1.0:** Cuando `counterpart_rate == 1.0` exacto (misma moneda o paridad 1:1),
se muestra directo sin inversión. La condición es estricta `< 1.0`, no `<= 1.0`.

```python
user_counterpart_rate = fields.Float(
    compute="_compute_user_counterpart_rate",
    inverse="_inverse_user_counterpart_rate",
    store=False, digits=0, min_display_digits=2)

@api.depends("counterpart_rate")
def _compute_user_counterpart_rate(self):
    for rec in self:
        rate = rec.counterpart_rate
        if rate and rate < 1.0:
            rec.user_counterpart_rate = 1.0 / rate
        else:
            rec.user_counterpart_rate = rate or 0.0

def _inverse_user_counterpart_rate(self):
    for rec in self:
        user_rate = rec.user_counterpart_rate
        if not user_rate:
            continue
        if rec.counterpart_rate and rec.counterpart_rate < 1.0:
            rec.counterpart_rate = 1.0 / user_rate
        else:
            rec.counterpart_rate = user_rate
```

La vista muestra `user_counterpart_rate`. El label es dinámico:
- Si `counterpart_rate < 1.0` → `1 {counterpart_currency_id} = X {currency_id}`
- Si `counterpart_rate >= 1.0` → `1 {currency_id} = X {counterpart_currency_id}`

**Regla de prioridad de actualización (campos bidireccionales):**
1. Usuario modifica `counterpart_currency_amount` →
   recalcular `counterpart_rate = counterpart_currency_amount / amount`
2. Usuario modifica `user_counterpart_rate` (via inverse) →
   recalcular `counterpart_currency_amount = amount × counterpart_rate`
3. Usuario modifica `amount` →
   recalcular `counterpart_currency_amount` manteniendo tasa actual

---

## Casos de uso

### Sin reconcile (B1 = B2 = B)

| # | Escenario | Monedas A→B→C | Input usuario | Sistema calcula |
|---|-----------|---------------|---------------|-----------------|
| 1 | Pago local simple | ARS→ARS→ARS | Monto: 10.000 ARS | Rates ocultos (1.0) |
| 2 | Pago divisa pura | USD→USD→ARS | Monto: 100 USD · Accounting Rate: 1.200 | Counterpart rate oculto (1.0) |
| 3 | Compra de divisa | ARS→USD→ARS | Total deuda: 100 USD · Counterpart rate: 1.250 | Monto A: 125.000 ARS (calculado) |
| 4 | Venta de divisa | USD→ARS→ARS | Total deuda: 120.000 ARS · Counterpart rate: 1.200 | Monto A: 100 USD (calculado) |
| 5 | Arbitraje cruzado | USD→EUR→ARS | Total deuda: 100 EUR · C.rate: 1.10 · A.rate: 1.200 | Monto A: 110 USD (por transitividad) |
| 6 | Pago mixto/parcial | ARS→USD→ARS | Monto A: 60.000 ARS · C.rate: 1.200 | Deuda B: 50 USD (recalculado inverso) |
| 7 | Pago anticipado | ARS→USD→ARS | Monto A libre · `counterpart_currency_id` editable | `user_counterpart_rate` visible |

### Con `reconcile_on_company_currency`

| # | Escenario | A / B1 / B2 / C | Input usuario |
|---|-----------|-----------------|---------------|
| 8 | Forzar divisa en pago ARS | ARS/USD/ARS/ARS | Monto: 60.000 ARS · C.rate: 1.200 |
| 9 | Pago USD de deuda ARS | USD/USD/ARS/ARS | Monto: 1.000 USD · A.rate: 1.200 |
| 10 | Arbitraje informativo | EUR/USD/ARS/ARS | Monto: 100 EUR · C.rate: 1.10 · A.rate: 1.200 |

---

## Mapa de cambios en campos

### Campos nuevos / modificados

| Campo | Cambio | Moneda | Tipo |
|-------|--------|--------|------|
| `counterpart_currency_id` | Nuevo (lógica completa) | — | Computed stored editable |
| `destination_currency_id` | Nuevo | — | Computed non-stored |
| `accounting_rate` | Renombrado desde `exchange_rate` (non-stored → stored, formato Odoo nativo) | — | Stored editable |
| `user_accounting_rate` | Nuevo, UX helper (inverso de `accounting_rate`) | — | Computed non-stored + inverse |
| `counterpart_rate` | Renombrado desde `counterpart_exchange_rate` (stored, formato invertido → Odoo nativo) | — | Stored editable |
| `user_counterpart_rate` | Nuevo, UX helper (inverso condicional de `counterpart_rate`) | — | Computed non-stored + inverse |
| `counterpart_currency_amount` | Adaptar lógica, moneda a `destination_currency_id` | `destination_currency_id` | Computed stored + inverse |
| `selected_debt` | Adaptar moneda y lógica compute (ver sección dedicada) | `destination_currency_id` | Computed |
| `unreconciled_amount` | Adaptar moneda | `destination_currency_id` | Normal |
| `to_pay_amount` | Adaptar moneda | `destination_currency_id` | Computed + inverse |
| `to_pay_amount_company_currency` | Nuevo: `to_pay_amount × accounting_rate` | `company_currency_id` | Computed |
| `write_off_amount` | Migrar moneda de `company_currency_id` a `destination_currency_id` (incluye migration de datos) | `destination_currency_id` | Normal |
| `withholdable_advanced_amount` | Mueve moneda a `destination_currency_id` (def. en `l10n_ar_tax`) | `destination_currency_id` | Computed stored editable |
| `withholdings_amount` | Mueve moneda a `destination_currency_id` (def. en `l10n_ar_tax`) | `destination_currency_id` | Computed |
| `payment_difference` | Adaptar moneda | `destination_currency_id` | Computed |
| `payment_total` | Adaptar moneda | `destination_currency_id` | Computed |
| `matched_amount` | Adaptar moneda | `destination_currency_id` | Computed |
| `unmatched_amount` | Adaptar moneda | `destination_currency_id` | Computed |

### Campos deprecated (eliminar como fields de Odoo, backup de columna SQL)

| Campo | Acción |
|-------|--------|
| `force_amount_company_currency` | Eliminar. Reemplazado por `accounting_rate` |
| `amount_company_currency` | Eliminar |
| `amount_company_currency_signed_pro` | Evaluar si se puede eliminar |
| `exchange_rate` | Eliminar (reemplazado por `accounting_rate` stored) |
| `other_currency` | Evaluar eliminar (reemplazable por `currency_id != company_currency_id`) |
| `selected_debt_untaxed` | Evaluar eliminar (definido en `l10n_ar_tax`) |
| `matched_amount_untaxed` | Evaluar eliminar (definido en `l10n_ar_tax`) |

> Usar `openupgrade.copy_columns(env.cr, _column_copy)` para backup antes de drop.

### Convención para campos de tasa (Float)

```python
my_rate_field = fields.Float(string='...', digits=0, min_display_digits=2)
# digits=0 → máxima precisión en almacenamiento
# min_display_digits=2 → visualización adaptativa
```

---

## Lógica de `selected_debt` con moneda `destination_currency_id`

Al migrar `selected_debt` a `destination_currency_id`, el compute debe seleccionar el
campo correcto de las líneas de deuda según la moneda de destino:

```python
@api.depends("to_pay_move_line_ids", "destination_currency_id")
def _compute_selected_debt(self):
    for rec in self:
        sign = -1.0 if rec.partner_type == "supplier" else 1.0
        if rec.destination_currency_id and rec.destination_currency_id != rec.company_currency_id:
            # Deuda en divisa: usar amount_residual_currency
            amount = sum(rec.to_pay_move_line_ids._origin.mapped("amount_residual_currency"))
        else:
            # Deuda en moneda de la compañía: usar amount_residual
            amount = sum(rec.to_pay_move_line_ids._origin.mapped("amount_residual"))
        rec.selected_debt = amount * sign
```

La misma lógica aplica para `matched_amount` y `unmatched_amount`: cuando
`destination_currency_id != company_currency_id`, los importes deben expresarse
en moneda B (divisa) y no en moneda C (compañía).

---

## Cambios en `account.move.line`

### Campo `payment_matched_amount`

Actualmente computa en `company_currency_id`. Reimplementar para expresar el importe
cancelado en **moneda B** (`destination_currency_id`).

Se agrega un campo auxiliar `payment_matched_currency_id` para que el campo monetary
sepa en qué moneda está.

```python
class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    payment_matched_currency_id = fields.Many2one(
        'res.currency',
        string="Payment Matched Currency",
        compute='_compute_payment_matched_values',
    )

    payment_matched_amount = fields.Monetary(
        compute="_compute_payment_matched_values",
        currency_field="payment_matched_currency_id",
        string="Paid Amount",
    )

    @api.depends_context("matched_payment_ids")
    def _compute_payment_matched_values(self):
        payment_ids = self._context.get("matched_payment_ids")
        if not payment_ids:
            self.payment_matched_amount = 0.0
            self.payment_matched_currency_id = False
            return

        payments = self.env["account.payment"].browse(payment_ids)
        main_payment = payments[0]

        target_currency = main_payment.destination_currency_id or main_payment.company_currency_id
        accounting_rate = main_payment.accounting_rate or 1.0
        counterpart_rate = main_payment.counterpart_rate or 1.0

        for rec in self:
            rec.payment_matched_currency_id = target_currency

            matched_partials = (
                rec.matched_debit_ids.filtered(
                    lambda p: p.debit_move_id.payment_id in payments)
                | rec.matched_credit_ids.filtered(
                    lambda p: p.credit_move_id.payment_id in payments)
            )

            total_amount_company_currency = sum(matched_partials.mapped('amount'))

            if total_amount_company_currency == 0:
                rec.payment_matched_amount = 0.0
                continue

            # Conversión C → A → B
            # En formato Odoo nativo: rate = to_currency / from_currency
            # accounting_rate convierte C → A
            # counterpart_rate convierte A → B1
            amount_in_a = total_amount_company_currency * accounting_rate
            amount_in_b = amount_in_a / counterpart_rate if counterpart_rate else amount_in_a

            rec.payment_matched_amount = amount_in_b
```

> **NOTA sobre conversión con formato Odoo nativo:** Verificar la dirección de las
> tasas durante la implementación. En Odoo `_get_conversion_rate(from, to)` devuelve
> `to/from`, así que `amount_from * rate = amount_to`.

---

## `_prepare_move_lines_per_type` — revisión completa

Este es el método central que genera los asientos del pago. El código actual cubre
parcialmente los casos del modelo tri-monetario:

- `force_amount_company_currency` se usa para forzar el balance en C → **se elimina**, reemplazar por `accounting_rate`
- `_use_counterpart_currency()` solo activa cuando `A == C` → **ampliar** para cubrir todos los casos de la tabla
- Los 5 escenarios sin reconcile y los 3 con reconcile deben generar asientos correctos

**Tareas concretas:**
1. Eliminar la lógica de `force_amount_company_currency` y reemplazar por cálculo via `accounting_rate`
2. Reescribir `_use_counterpart_currency()` o eliminarla e inline la lógica en el método principal
3. La línea de liquidez siempre usa `currency_id` (A) con `amount_currency` en A y `balance` calculado via `accounting_rate`
4. La línea de contrapartida usa `counterpart_currency_id` (B1) con `amount_currency` en B1 y `balance` cuadrado por diferencia
5. Validar que cada caso de la tabla de casos de uso genera los asientos esperados
6. Los tests de integración deben verificar `balance` y `amount_currency` de cada línea generada

---

## Adaptaciones en métodos auxiliares

### `_get_trigger_fields_to_synchronize`

El código actual agrega `force_amount_company_currency`, `counterpart_exchange_rate`,
`counterpart_currency_id` al resultado de `super()`. Con el refactor:

```python
@api.model
def _get_trigger_fields_to_synchronize(self):
    res = super()._get_trigger_fields_to_synchronize()
    if self.mapped("move_id"):
        res = res + (
            "accounting_rate",
            "counterpart_rate",
            "counterpart_currency_id",
        )
    return res + (
        "write_off_amount",
        "write_off_type_id",
    )
```

### `_create_paired_internal_transfer_payment`

El código actual propaga `force_amount_company_currency` en contexto para la
transferencia interna pareada. Con el refactor, propagar `accounting_rate`:

```python
def _create_paired_internal_transfer_payment(self):
    for rec in self:
        super(
            AccountPayment,
            rec.with_context(default_accounting_rate=rec.accounting_rate),
        )._create_paired_internal_transfer_payment()
```

---

## Migration scripts

### Estrategia general

Los campos stored nuevos se pueblan via SQL **antes** de que el ORM cargue la nueva lógica.
Si la columna ya tiene datos cuando Odoo monta el módulo, no encola recomputo.

### `pre_migrate.py`

```python
from openupgradelib import openupgrade

def migrate(cr, version):
    # 1. counterpart_exchange_rate → counterpart_rate
    #    El valor stored actual es user-friendly (ej: 1500).
    #    El nuevo campo usa formato Odoo nativo (ej: 0.000667) → invertir.
    openupgrade.rename_columns(cr, {
        "account_payment": [("counterpart_exchange_rate", "counterpart_rate")]
    })
    cr.execute("""
        UPDATE account_payment
        SET counterpart_rate = 1.0 / counterpart_rate
        WHERE counterpart_rate IS NOT NULL AND counterpart_rate != 0;
    """)

    # 2. accounting_rate: nueva columna, poblar desde amount y amount_company_currency
    #    exchange_rate era non-stored, no hay columna que renombrar.
    cr.execute("""
        ALTER TABLE account_payment
        ADD COLUMN IF NOT EXISTS accounting_rate NUMERIC;
    """)
    cr.execute("""
        UPDATE account_payment
        SET accounting_rate = CASE
            WHEN amount IS NOT NULL AND amount != 0
                THEN amount_company_currency / amount
            ELSE 1.0
        END
        WHERE accounting_rate IS NULL;
    """)

    # 3. Backup de campos deprecated antes de drop
    openupgrade.copy_columns(cr, {
        "account_payment": [
            ("force_amount_company_currency", "x_bkp_force_amount_company_currency", None),
            ("amount_company_currency", "x_bkp_amount_company_currency", None),
            ("write_off_amount", "x_bkp_write_off_amount", None),
        ]
    })

    # 4. write_off_amount: migrar de company_currency a destination_currency
    #    Para pagos donde el counterpart_rate != 0, convertimos el importe.
    #    write_off_amount_new = write_off_amount_old / counterpart_rate (Odoo nativo)
    #    Nota: counterpart_rate ya está invertido en paso 1.
    cr.execute("""
        UPDATE account_payment
        SET write_off_amount = write_off_amount / counterpart_rate
        WHERE write_off_amount IS NOT NULL
          AND write_off_amount != 0
          AND counterpart_rate IS NOT NULL
          AND counterpart_rate != 0
          AND counterpart_rate != 1.0;
    """)
```

### `post_migrate.py`

```python
def migrate(cr, version):
    # Verificación: ningún registro debería tener accounting_rate o counterpart_rate en NULL
    cr.execute("""
        SELECT COUNT(*) FROM account_payment
        WHERE state != 'draft'
          AND (accounting_rate IS NULL OR counterpart_rate IS NULL);
    """)
    count = cr.fetchone()[0]
    if count:
        import logging
        logging.getLogger(__name__).warning(
            "account_payment_pro migration: %d posted payments with NULL rates", count
        )
```

---

## Vista del formulario de pago

### Sección deuda a pagar / pagada (`to_pay_move_line_ids`, `matched_move_line_ids`)

- Si `destination_currency_id != company_currency_id`:
  mostrar `amount_residual_currency` visible, `amount_residual` con optional hide
- Si `destination_currency_id == company_currency_id`:
  mostrar `amount_residual` visible, `amount_residual_currency` con optional hide

### Sección montos

```xml
<div name="amount_div" position="after">
    <label for="user_counterpart_rate" string="Rate"
        invisible="currency_id == counterpart_currency_id
                   or counterpart_currency_id == company_currency_id"/>
    <div name="counterpart_rate_div" class="d-flex gap-1 text-muted"
        invisible="currency_id == counterpart_currency_id
                   or counterpart_currency_id == company_currency_id">
        <span>1</span>
        <field name="currency_id" readonly="True" options="{'no_open': True}" class="w-auto"/>
        <span>=</span>
        <field name="user_counterpart_rate" readonly="state != 'draft'" style="max-width: 21ch;"/>
        <field name="counterpart_currency_id" readonly="True" options="{'no_open': True}" class="w-auto"/>
    </div>

    <field name="company_currency_id" invisible="True"/>
    <field name="destination_currency_id" invisible="True"/>
    <field name="counterpart_currency_amount" string="Amount in"
        invisible="currency_id == counterpart_currency_id"/>
    <label for="write_off_amount" string="Write Off"
        invisible="not write_off_available or is_internal_transfer or not use_payment_pro"/>
    <div name="write_off_amount" class="o_row"
        invisible="not write_off_available or is_internal_transfer or not use_payment_pro">
        <field name="write_off_amount" readonly="state != 'draft'"/>
        <field name="write_off_type_id" placeholder="Write-off type"
            invisible="not write_off_amount" readonly="state != 'draft'"
            required="write_off_amount" options="{'no_create': True, 'no_open': True}"/>
    </div>
    <label for="payment_total" readonly="state != 'draft'"
        invisible="not use_payment_pro or is_internal_transfer"/>
    <div name="payment_total" invisible="not use_payment_pro or is_internal_transfer">
        <field name="payment_total" class="oe_inline"/>
        <span invisible="state != 'draft'" class="text-muted">
            (difference <field name="payment_difference" class="oe_inline"/>)
        </span>
    </div>
    <label for="user_accounting_rate" string="Rate"
        invisible="currency_id == company_currency_id"/>
    <div name="accounting_rate_div" class="d-flex gap-1 text-muted"
        invisible="currency_id == company_currency_id">
        <span>1</span>
        <field name="currency_id" readonly="True" options="{'no_open': True}" class="w-auto"/>
        <span>=</span>
        <field name="user_accounting_rate" readonly="state != 'draft'" style="max-width: 21ch;"/>
        <field name="company_currency_id" readonly="True" options="{'no_open': True}" class="w-auto"/>
    </div>
</div>
```

Label de `counterpart_currency_amount`: usar `string="Amount in"` estático.
El campo monetary ya muestra el símbolo de la moneda.

---

## Criterios de aceptación

- [ ] Los 10 casos de uso tienen test de integración (verificar `balance` y `amount_currency` de cada línea de asiento)
- [ ] Los tests existentes pasan o se actualizan justificadamente
- [ ] Los campos deprecated se eliminan como fields de Odoo
- [ ] Backup de columnas SQL via `openupgrade.copy_columns` está en el migration script
- [ ] `l10n_ar_tax` sigue funcionando (campos de retenciones en `destination_currency_id`)
- [ ] No se rompe la conciliación con `reconcile_on_company_currency`
- [ ] Las tasas de cambio se almacenan con `digits=0, min_display_digits=2`
- [ ] Post-migración: cero pagos posted con `accounting_rate` o `counterpart_rate` en NULL
- [ ] `counterpart_rate` almacena en formato Odoo nativo (< 1 para ARS/USD)
- [ ] `write_off_amount` migrado a `destination_currency_id`
- [ ] `_get_trigger_fields_to_synchronize` actualizado con los campos renombrados
- [ ] `_create_paired_internal_transfer_payment` propaga `accounting_rate` en vez de `force_amount_company_currency`

---

## Impacto en otros módulos / equipos

| Módulo | Equipo | Tipo | Acción requerida |
|--------|--------|------|-----------------|
| `l10n_ar_tax` | Equipo Contable | Breaking: campos de moneda cambian a `destination_currency_id` | Review + adaptar campos `withholdable_advanced_amount`, `withholdings_amount`, `matched_amount_untaxed` |
| `l10n_ar_tax` | Equipo Contable | Breaking: `exchange_rate` cambia semántica → `accounting_rate` en formato Odoo nativo | `_prepare_move_withholding_lines` usa `self.exchange_rate or 1.0` → adaptar fórmula. **Scope: iteración siguiente.** |
| `account_ux` | ADHOC | Dependencia nueva: provee `reconcile_on_company_currency` en `res.company` | Agregar al `__manifest__.py` de `account_payment_pro` |
| `account` (Odoo SA) | — | Sin modificaciones directas | Verificar que la herencia no rompa nada en v19 |
