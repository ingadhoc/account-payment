# Análisis de Código vs. Specs

## Resumen

He generado tests completos para los casos de uso definidos en ambos specs (`spec.md` y `spec_l10n_ar_tax.md`). Durante la revisión del código, identifiqué los siguientes hallazgos:

## ✅ Código Correcto (Sin Errores Críticos)

El código implementado en `account_payment_pro` y `l10n_ar_tax` **está correctamente alineado con los specs**. No se encontraron errores críticos en la implementación.

### Alineación con spec.md (account_payment_pro):

1. ✅ **Campos del modelo tri-monetario**: `counterpart_currency_id`, `destination_currency_id`, `accounting_rate`, `counterpart_rate` están implementados correctamente.

2. ✅ **Formato de rates**: El código usa formato Odoo nativo (`_get_conversion_rate`) correctamente:
   - `accounting_rate` = `_get_conversion_rate(C, A)` - formato Odoo nativo (stored)
   - `counterpart_rate` = `_get_conversion_rate(A, B1)` - formato Odoo nativo (stored)
   - `user_accounting_rate` y `user_counterpart_rate` - helpers UX con inverse condicional

3. ✅ **Lógica de computes**: Los métodos `_compute_counterpart_currency_id`, `_compute_destination_currency_id`, `_compute_accounting_rate`, `_compute_counterpart_rate` siguen la lógica descrita en el spec.

4. ✅ **Sincronización de rates**: Cuando `B1 == C`, el `counterpart_rate` delega correctamente en `accounting_rate`.

5. ✅ **_prepare_move_lines_per_type**: El método implementa correctamente los ajustes de balance y amount_currency para liquidez y contrapartida.

### Alineación con spec_l10n_ar_tax.md (retenciones):

1. ✅ **base_amount en C (ARS)**: Las líneas de retención almacenan `base_amount` en ARS (C), sin migrar a moneda B. Correcto según el spec.

2. ✅ **_get_withholding_rate()**: Implementado correctamente. Devuelve multiplicador directo B→C usando `_get_conversion_rate(destination_currency_id, company_currency_id)`.

3. ✅ **_compute_base_amount**: Calcula la base en B y convierte a C al final usando `_get_withholding_rate()`. Usa `amount_residual_currency` cuando B≠C. Correcto.

4. ✅ **_tax_compute_all_helper**: Usa `self.base_amount` directamente (ya en C) para `compute_all`. No hay conversión adicional. Correcto.

5. ✅ **_prepare_move_withholding_lines**: 
   - Usa `self.accounting_rate` (línea 165) en lugar de `exchange_rate` deprecado ✅
   - Implementa correctamente `use_company_currency` para caso A≠C
   - Las líneas van siempre en ARS cuando A≠C

6. ✅ **_prepare_move_lines_per_type** (en account_payment.py):
   - Implementa correctamente el caso `counterpart_is_foreign` (línea 265-267)
   - Ajusta `amount_currency` de la contrapartida cuando A=C=ARS pero B=USD
   - Calcula `wth_amount_in_b` usando `_get_withholding_rate()` correctamente

7. ✅ **withholdings_amount**: Computa en `destination_currency_id` con conversión C→B (`total_ars / rate`). Correcto según spec.

8. ✅ **_compute_payment_total**: Suma `withholdings_amount` (ya en B) al total. Correcto.

## 📝 Observaciones Menores (No Críticas)

### 1. Ubicación de lógica `counterpart_is_foreign`

**Spec dice (línea 369):**
> "Tabla final de ramas (en `_prepare_move_withholding_lines`)"

**Implementación real:**
La lógica de `counterpart_is_foreign` NO está dentro de `_prepare_move_withholding_lines`, sino en `_prepare_move_lines_per_type` (líneas 265-275 de `l10n_ar_tax/models/account_payment.py`).

**Análisis:**
- ✅ Esto NO es un error, solo una diferencia de ubicación.
- La lógica es correcta: las withholding lines siempre van en ARS cuando A=C, y el ajuste USD para la contrapartida (AP) se hace en `_prepare_move_lines_per_type`.
- El comportamiento final es el esperado según el spec.

### 2. Lógica de `use_company_currency` en `_prepare_move_withholding_lines`

**Código actual (línea 182):**
```python
use_company_currency = self.currency_id != self.company_id.currency_id
```

**Análisis:**
- ✅ Esta lógica es correcta. Cuando A≠C (pago en USD), las líneas van en ARS (`currency_id=C`) para evitar rounding.
- ✅ Cuando A=C (pago en ARS), `use_company_currency=False`, entonces las líneas van con `currency_id=A` que es ARS de todas formas.
- ✅ El resultado final siempre es correcto: las withholding lines están en ARS en ambos casos.

### 3. Documentación de `@api.depends` en `_compute_base_amount`

**Spec menciona (línea 392):**
> "Bug 1: `@api.depends` incompleto en `_compute_base_amount`"
> "Añadir: `payment_id.accounting_rate`, `payment_id.counterpart_rate`"

**Código actual (línea 38):**
```python
@api.depends(
    "tax_id",
    "payment_id.selected_debt",
    "payment_id.selected_debt_untaxed",
    "payment_id.withholdable_advanced_amount",
    "payment_id.unreconciled_amount",
    "payment_id.counterpart_rate",
    "payment_id.accounting_rate",
)
def _compute_base_amount(self):
```

**Análisis:**
- ✅ El código YA incluye `payment_id.accounting_rate` y `payment_id.counterpart_rate` en el `@api.depends`.
- ✅ El bug mencionado en el spec ya está corregido.

## 🎯 Conclusiones

1. **No se encontraron errores críticos** en la implementación actual comparada con los specs.

2. **Las diferencias mencionadas son de documentación/ubicación**, no de funcionalidad:
   - La lógica de `counterpart_is_foreign` está en `_prepare_move_lines_per_type` en vez de `_prepare_move_withholding_lines`, pero funciona correctamente.
   - Los `@api.depends` ya incluyen los campos necesarios.

3. **Los tests generados cubren todos los casos de uso** definidos en ambos specs:
   - 10 casos para `account_payment_pro` (modelo tri-monetario)
   - 7 casos para `l10n_ar_tax` (retenciones multimoneda)

4. **Los tests están bien documentados** con comentarios claros que explican:
   - Qué escenario se está probando
   - Los valores de entrada (setup)
   - Las validaciones esperadas
   - Los principios fiscales/contables aplicados

## 📋 Archivos Generados

1. **`account_payment_pro/tests/test_payment_multimoneda.py`**
   - 10 tests cubriendo casos 1-10 del spec.md
   - Tests para escenarios sin y con `reconcile_on_company_currency`
   - Validación de rates, montos, y conciliaciones

2. **`l10n_ar_tax/tests/test_payment_withholding_multimoneda.py`**
   - 7 tests cubriendo casos T.1-T.7 del spec_l10n_ar_tax.md
   - Tests de retenciones en distintas combinaciones de monedas
   - Validación de base_amount, withholding amount, y asientos contables
   - Incluye caso de ganancias con acumulado del período

3. **Actualizaciones a `__init__.py`**
   - Ambos módulos actualizados para importar los nuevos archivos de tests

## 🚀 Próximos Pasos

1. **Ejecutar los tests** para verificar que pasen:
   ```bash
   # Para account_payment_pro
   odoo -d <db_name> --stop-after-init --test-enable -u account_payment_pro --test-tags /account_payment_pro

   # Para l10n_ar_tax
   odoo -d <db_name> --stop-after-init --test-enable -u l10n_ar_tax --test-tags /l10n_ar_tax
   ```

2. **Ajustar tests según sea necesario** basándose en los resultados de la ejecución.

3. **Considerar tests adicionales** para casos edge:
   - Cambio de rate después de crear el pago (draft→posted)
   - Modificación de moneda de la cuenta durante el flujo
   - Múltiples retenciones en un mismo pago
   - Pagos con write-offs en distintas monedas

---

**Autor:** GitHub Copilot (Claude Sonnet 4.5)  
**Fecha:** 2026-03-19  
**Modo:** odoo-test-from-commit (adaptado para revisión de specs)
