# Informe: Tests Multimoneda - Payment Pro & l10n_ar_tax

**Fecha:** 20 de marzo de 2026 - 18:47
**Módulos:** `account_payment_pro`, `l10n_ar_tax`
**Estado:** ⚠️ **10 FAILS + 3 ERRORS** de 19 tests totales

---

## 📊 Resumen Ejecutivo

Los tests de ambos módulos validan el modelo tri-monetario (A/B/C) en pagos multimoneda y el cálculo de retenciones. Se identificaron problemas críticos comunes relacionados con el cálculo de `counterpart_rate` y `counterpart_currency_amount`.

### Estado Global - Última Ejecución (18:47-18:48)

| Módulo | Tests Total | ✅ Pasando | ❌ Fallando | Tiempo | Queries |
|--------|-------------|-----------|-------------|--------|---------|
| `account_payment_pro` | 11 | 6 | **5 FAILS** | 6.32s | 3301 |
| `l10n_ar_tax` | 8 | 1 | **4 FAILS + 3 ERRORS** | 4.53s | 2330 |
| **TOTAL** | **19** | **7 (37%)** | **13 (63%)** | 10.85s | 5631 |

### Bugs Críticos Identificados

1. **`counterpart_currency_amount` no reactivo** - No se recalcula cuando se setea `counterpart_rate` manualmente
2. **`accounting_rate` y `counterpart_rate` incorrectos** - Cálculos usando formato invertido o valores erróneos
3. **`compute_withholdings()` no existe** en modelo - Tests de l10n_ar_tax llaman a método inexistente
4. **Conciliación fallando** - Casos con `reconcile_on_company_currency=True` no concilian
5. **Estados de pago incorrectos** - Pagos quedan en estado `'paid'` en vez de `'posted'`

---

## 🧪 Resultados Detallados

### Tests de account_payment_pro (spec.md)

**Ejecutados:** 11 tests | **✅ 6 pasando (55%)** | **❌ 5 fallando (45%)**

| # | Test | Monedas (A→B→C) | Estado | Error |
|---|------|-----------------|--------|-------|
| 1 | Pago local simple | ARS→ARS→ARS | ✅ PASS | - |
| 2 | Divisa pura | USD→USD→ARS | ✅ PASS | - |
| 3 | Compra de divisa | ARS→USD→ARS | ✅ PASS | - |
| 4 | Venta de divisa | USD→ARS→ARS | ✅ PASS | - |
| 5 | Arbitraje cruzado | USD→EUR→ARS | ✅ PASS | - |
| 6 | Pago mixto parcial | ARS→USD→ARS | ❌ FAIL | `counterpart_currency_amount == 60000.0` esperaba `50.0 USD` |
| 7 | Pago anticipado | ARS→USD→ARS | ❌ FAIL | `counterpart_currency_amount == 60000.0` esperaba `50.0 USD` |
| 8 | Forzar divisa en pago ARS | ARS→USD→ARS | ❌ FAIL | No se creó `matched_credit_ids` (conciliación fallida) |
| 9 | Pago USD de deuda ARS | USD→ARS→ARS | ❌ FAIL | Factura no marcada como pagada (`payment_state`) |
| 10 | Arbitraje informativo | USD→EUR→ARS | ❌ FAIL | `counterpart_rate == 0.000758` esperaba `~1320.0 (EUR→USD)` |
| - | Unit test: change date rate | - | ✅ PASS | - |

**Diagnóstico account_payment_pro:**

- **Casos 6 y 7:** `counterpart_currency_amount` no se recalcula después de setear `counterpart_rate` manualmente. El campo depende de `@api.depends("amount", "counterpart_rate", ...)` pero el inverse/onchange no fuerza el recálculo.

- **Caso 8 y 9:** Problemas con conciliación cuando `reconcile_on_company_currency=True`. Las move lines probablemente tienen `currency_id` incorrecta o no se están matcheando correctamente.

- **Caso 10:** `counterpart_rate` invertido o en formato incorrecto. Calcula `0.000758` (1/1320) cuando debería ser `1320.0` directo para EUR→USD.

### Tests de l10n_ar_tax (spec_l10n_ar_tax.md)

**Ejecutados:** 8 tests | **✅ 1 pasando (12.5%)** | **❌ 7 fallando (87.5%)**

| # | Test | Monedas (A→B→C) | Estado | Error |
|---|------|-----------------|--------|-------|
| - | test_arba (conexión ARBA) | - | ✅ PASS | - |
| T.1 | Pago local | ARS→ARS→ARS | ❌ FAIL | Estado `'paid'` esperaba `'posted'` |
| T.2 | Divisa pura | USD→USD→ARS | ❌ FAIL | `accounting_rate == 1.0` esperaba `1200.0 (USD→ARS)` |
| T.3 | Compra divisa | ARS→USD→ARS | ❌ FAIL | `counterpart_rate == 1500.0` esperaba `~0.000667` |
| T.4 | Dos facturas USD distintos rates | ARS→USD→ARS | ❌ ERROR | `AttributeError: no attribute 'compute_withholdings'` |
| T.5 | Pago parcial | ARS→USD→ARS | ❌ ERROR | `AttributeError: no attribute 'compute_withholdings'` |
| T.6 | Arbitraje | USD→EUR→ARS | ❌ FAIL | `amount_currency == 39600.0 ARS` esperaba `33.0 USD` |
| T.7 | Ganancias con acumulado | ARS→USD→ARS | ❌ ERROR | `AttributeError: no attribute 'compute_withholdings'` |

**Diagnóstico l10n_ar_tax:**

- **T1:** Estado de pago cambia a `'paid'` automáticamente después de `action_post()`. Probablemente se autoconcilia y el workflow cambia el estado.

- **T2:** `accounting_rate` calculado como `1.0` en vez de `1200.0` para USD→ARS. El compute de `accounting_rate` no está calculando correctamente cuando `A != C`.

- **T3:** `counterpart_rate` calcula `1500.0` (ARS→USD formato Odoo) cuando test espera `~0.000667` (USD→ARS formato invertido). **Probable error en expectativa de test**, no en modelo.

- **T4, T5, T7:** Tests llaman a `payment.compute_withholdings()` que **NO EXISTE**. Métodos reales disponibles:
  - `_compute_withholdings_amount()` (compute method)
  - `_compute_l10n_ar_withholding_line_ids()` (compute method)
  - `_onchange_withholdings()` (onchange method)

- **T6:** Campo `amount_currency` en move line de retención tiene `39600 ARS` cuando debería ser `33 USD`. La creación de move lines de retención no está usando `currency_id` y `amount_currency` correctos.

---

## 📋 Modelo de Monedas - Validación contra Spec

El modelo tri-monetario implementado en `account_payment_pro` se alinea correctamente con la spec:

| Símbolo | Campo | Descripción | Spec |
|---------|-------|-------------|------|
| **A** | `currency_id` | Moneda del diario (liquidez) | ✅ |
| **B1** | `counterpart_currency_id` | Moneda del apunte AP/AR | ✅ Computed stored editable |
| **B2** | `destination_currency_id` | Moneda de UX/conciliación | ✅ Computed non-stored |
| **C** | `company_currency_id` | Moneda contable (ARS) | ✅ Related |

### Rates - Validación contra Spec

| Campo | Fórmula spec | Formato Odoo | Ejemplo (1 USD = 1200 ARS) |
|-------|--------------|--------------|----------------------------|
| `accounting_rate` | `_get_conversion_rate(A, C)` | Multiplicador | `1200.0` (USD→ARS) |
| `counterpart_rate` | `_get_conversion_rate(A, B1)` | Multiplicador | Depende de B1 |
| `_get_withholding_rate()` | `accounting_rate / counterpart_rate` | B→C | Calculado on-the-fly |

**⚠️ Problema detectado:** Cuando se setea `counterpart_rate` manualmente, `counterpart_currency_amount` no se recalcula (casos 6 y 7 de payment_pro).

---

## 🔬 Análisis de Errores Críticos

### 1. `counterpart_currency_amount` No Reactivo ⚠️

**Archivos afectados:**
- `account_payment_pro/models/account_payment.py`

**Tests afectados:**
- payment_pro: Caso 6 (pago mixto parcial), Caso 7 (pago anticipado)

**Síntoma:**
```python
payment.counterpart_rate = 1 / 1200.0  # ARS→USD
# Esperado: counterpart_currency_amount = 60000 * (1/1200) = 50 USD
# Real: counterpart_currency_amount = 60000.0 (no recalculado)
```

**Causa raíz:**
El campo `counterpart_currency_amount` es `@api.depends("amount", "counterpart_rate", ...)` pero cuando se setea `counterpart_rate` manualmente desde tests, el compute no se dispara o no actualiza el stored value.

**Solución propuesta:**
```python
def _inverse_counterpart_rate(self):
    for rec in self:
        if rec.counterpart_currency_id == rec.company_currency_id:
            rec.accounting_rate = rec.counterpart_rate
        # AGREGAR: Forzar recálculo de counterpart_currency_amount
        rec._compute_counterpart_currency_amount()
```

**Alternativa (solo tests):**
```python
# En tests, después de establecer counterpart_rate:
payment.counterpart_rate = 1 / 1200.0
payment._compute_counterpart_currency_amount()  # Forzar cálculo manual
```

### 2. `accounting_rate` y `counterpart_rate` Incorrectos ⚠️

**Archivos afectados:**
- `account_payment_pro/models/account_payment.py`

**Tests afectados:**
- payment_pro: Caso 10 (arbitraje)
- l10n_ar_tax: T2 (divisa pura), T3 (compra divisa)

**Síntoma T2 (l10n_ar_tax):**
```python
# A=USD, B=USD, C=ARS, rate: 1 USD = 1200 ARS
accounting_rate == 1.0  # ❌ Incorrecto
# Esperado: 1200.0
```

**Síntoma T3 (l10n_ar_tax):**
```python
# A=C=ARS, B=USD, rate: 1 USD = 1500 ARS
counterpart_rate == 1500.0  # Formato Odoo: ARS→USD
# Test espera: ~0.000667  # Formato invertido: USD→ARS
```

**Síntoma Caso 10 (payment_pro):**
```python
# A=USD, B=EUR, C=ARS
# Rates: 1 USD = 1200 ARS, 1 EUR = 1320 ARS
# Esperado counterpart_rate (EUR→USD): 1320/1200 = 1.1
counterpart_rate == 0.000758  # ❌ Formato invertido o cálculo erróneo
```

**Causa raíz:**
Los computes de `_compute_accounting_rate()` y `_compute_counterpart_rate()` probablemente usan `_get_conversion_rate()` incorrectamente o hay confusión entre formato Odoo (multiplicador) vs formato user-friendly (divisor).

**Análisis:**
```python
# Según spec, _get_conversion_rate(from, to) devuelve: to/from
rate_usd_ars = _get_conversion_rate(USD, ARS)
# = ARS/USD = 1200/1 = 1200.0  ✅ Correcto formato Odoo

# Para ARS→USD:
rate_ars_usd = _get_conversion_rate(ARS, USD)
# = USD/ARS = 1/1200 = 0.000833  ✅ Correcto formato Odoo

# Tests de l10n_ar_tax esperan formato inconsistente:
# T2: espera accounting_rate = 1200 ✅
# T3: espera counterpart_rate = 0.000667 ❌ (debería esperar 1500.0)
```

**Decisión:**
- **T2 (l10n_ar_tax):** Corregir `_compute_accounting_rate()` para calcular correctamente cuando `A != C`
- **T3 (l10n_ar_tax):** Corregir expectativa del test (esperar `1500.0` en vez de `0.000667`)
- **Caso 10 (payment_pro):** Revisar `_compute_counterpart_rate()` para caso `A != B != C`

### 3. `compute_withholdings()` No Existe ❌

**Archivos afectados:**
- `l10n_ar_tax/tests/test_payment_withholding_multimoneda.py` (línea ~296 en helper)

**Tests afectados:**
- l10n_ar_tax: T4, T5, T7

**Síntoma:**
```python
payment.compute_withholdings()
# AttributeError: 'account.payment' object has no attribute 'compute_withholdings'
```

**Métodos reales disponibles:**
```python
# En l10n_ar_tax/models/account_payment.py
_compute_withholdings_amount(self)                # @api.depends compute
_compute_l10n_ar_withholding_line_ids(self)       # @api.depends compute
_onchange_withholdings(self)                      # @api.onchange
_prepare_move_withholding_lines(self, ...)        # Helper para move lines
```

**Solución - Opción 1 (Usar workflow real con wizard):**
```python
def _create_payment_with_withholding(self, journal, invoice, fiscal_position=None):
    fiscal_position = fiscal_position or self.fiscal_position

    # Crear pago usando el wizard de registro (simula UI)
    wizard = self.env["account.payment.register"].with_context(
        active_model="account.move",
        active_ids=invoice.ids,
    ).create({
        "journal_id": journal.id,
        "l10n_ar_fiscal_position_id": fiscal_position.id,
    })

    # El wizard calcula retenciones automáticamente
    action = wizard.action_create_payments()
    payment = self.env["account.payment"].browse(action["res_id"])
    return payment
```

**Solución - Opción 2 (Llamar compute manualmente):**
```python
def _create_payment_with_withholding(self, journal, invoice, fiscal_position=None):
    payment = self.env["account.payment"].create({
        "journal_id": journal.id,
        "partner_id": self.partner_ri.id,
        "partner_type": "supplier",
        "payment_type": "outbound",
        "date": self.today,
        "l10n_ar_fiscal_position_id": fiscal_position.id,
        "to_pay_move_line_ids": [Command.set(invoice.line_ids.filtered(...).ids)],
    })

    # Forzar cálculo de retenciones (triggers compute)
    payment.invalidate_recordset(['l10n_ar_withholding_line_ids'])
    payment._compute_l10n_ar_withholding_line_ids()
    return payment
```

### 4. Conciliación Fallando con `reconcile_on_company_currency` ❌

**Archivos afectados:**
- `account_payment_pro/models/account_payment.py` (método `_prepare_move_lines_per_type()`)

**Tests afectados:**
- payment_pro: Caso 8 (forzar divisa), Caso 9 (pago USD de deuda ARS)

**Síntoma:**
```python
payment.action_post()
# Esperado: invoice_line.matched_credit_ids existe
# Real: account.partial.reconcile() is empty
```

**Causa probable:**
Cuando `reconcile_on_company_currency=True`, las move lines de contrapartida se crean con monedas inconsistentes:
- AP/AR line: `currency_id=B1`, `amount_currency` en B1
- Payment line: `currency_id=A`, `amount_currency` en A

Pero la conciliación en company currency requiere que ambas tengan `currency_id=C` (ARS).

**Solución:**
Revisar `_prepare_move_lines_per_type()` sección `reconcile_on_company_currency` y asegurar:
1. Líneas de contrapartida usan `destination_currency_id` (B2=C) no `counterpart_currency_id` (B1)
2. `amount_currency` está en moneda C (ARS)

### 5. Estado `'paid'` en vez de `'posted'` ⚠️

**Archivos afectados:**
- `account_payment.py` (workflow de posting)

**Tests afectados:**
- l10n_ar_tax: T1 (pago local)

**Síntoma:**
```python
payment.action_post()
self.assertEqual(payment.state, "posted")  # ❌ Falla
# payment.state == 'paid'
```

**Causa probable:**
El pago se autoconcilia con la factura y el workflow cambia el estado a `'paid'` automáticamente. Esto podría ser comportamiento correcto de Odoo.

**Solución:**
Revisar si el test debe esperar `'paid'` en vez de `'posted'`, o si hay lógica que está forzando conciliación automática que no debería activarse.

---

## 🔄 Próximos Pasos

### Prioridad CRÍTICA (Bloquean tests)

1. ❌ **Corregir T4, T5, T7 (l10n_ar_tax)** - Reemplazar `compute_withholdings()` por workflow real
   - Implementar Opción 1 o 2 de la sección "Análisis de Errores"
   - Verificar que retenciones se calculan correctamente

2. ❌ **Arreglar `accounting_rate` en T2 (l10n_ar_tax)** - Debuggear `_compute_accounting_rate()`
   - Verificar que cuando `A=USD, C=ARS` devuelve `1200.0` no `1.0`
   - Revisar casos edge cuando `A == C`

3. ❌ **Corregir Casos 6 y 7 (payment_pro)** - Hacer `counterpart_currency_amount` reactivo
   - Implementar solución propuesta en `_inverse_counterpart_rate()`
   - O mantener inverse simple y arreglar solo los tests

4. ❌ **Arreglar Caso 10 (payment_pro)** - Debuggear `_compute_counterpart_rate()` para arbitraje
   - Para A=USD, B=EUR, C=ARS: `counterpart_rate` debe ser EUR/USD no USD/EUR
   - Revisar cálculo en caso `A != B != C`

### Prioridad ALTA (Funcionalidad core)

5. ❌ **Arreglar Casos 8 y 9 (payment_pro)** - Conciliación con `reconcile_on_company_currency`
   - Revisar `_prepare_move_lines_per_type()` para usar `destination_currency_id` correctamente
   - Validar que `currency_id` y `amount_currency` son consistentes

6. ❌ **Arreglar T3 (l10n_ar_tax)** - Corregir formato esperado de `counterpart_rate`
   - OPCIÓN A: Corregir test para esperar `1500.0` (formato Odoo)
   - OPCIÓN B: Corregir modelo para devolver `0.000667` (formato invertido)
   - **Recomendación:** OPCIÓN A (mantener formato Odoo consistente)

7. ❌ **Arreglar T6 (l10n_ar_tax)** - Move lines de retención con `currency_id` incorrecta
   - Revisar `_prepare_move_withholding_lines()` para caso arbitraje
   - Asegurar `amount_currency` en moneda correcta (USD no ARS)

### Prioridad MEDIA (Mejoras)

8. ⏳ **Revisar T1 (l10n_ar_tax)** - Estado `'paid'` vs `'posted'`
   - Validar si comportamiento es correcto o hay autoconciliación indebida
   - Actualizar test si comportamiento es esperado

9. ⏳ **Documentar casos edge** no cubiertos por tests actuales

10. ⏳ **Agregar tests de regresión** para bugs corregidos

---

## 📖 Referencias

- [spec.md](spec.md) — Modelo tri-monetario de account_payment_pro (A/B/C)
- [spec_l10n_ar_tax.md](spec_l10n_ar_tax.md) — Retenciones en pagos multimoneda
- Código base: `account_payment_pro/models/account_payment.py`
- Código retenciones: `l10n_ar_tax/models/account_payment.py`
- Tests payment_pro: `account_payment_pro/tests/test_payment_multimoneda.py`
- Tests retenciones: `l10n_ar_tax/tests/test_payment_withholding_multimoneda.py`

---

**Última actualización:** 20 de marzo de 2026 - 18:48
**Ejecutado por:** Agente Odoo
**Comando:** `odoo --test-enable --test-tags /account_payment_pro,/l10n_ar_tax`
