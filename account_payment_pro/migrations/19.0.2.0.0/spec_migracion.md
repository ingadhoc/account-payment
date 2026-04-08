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

## Apéndice: fix para bases ya migradas con scripts viejos (rotos)



  ┌─────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │            Campo            │                                                 Estado actual                                                  │                        ¿Necesita fix?                        │
  ├─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ counterpart_currency_id     │ NULL para la mayoría (solo tenían valor los del caso a/b). El script viejo nunca lo pobló.                     │ SÍ — fix con la lógica 4.1–4.4 del script bueno              │
  ├─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ counterpart_rate            │ Para los que tenían counterpart_exchange_rate viejo: OK (1/old). Para los demás: el ORM lo computó como 1.0    │ SÍ parcialmente — recomputar solo para los que NO tenían     │
  │                             │ (porque B1=NULL).                                                                                              │ backup viejo, después de poblar B1                           │
  ├─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ accounting_rate             │ El ORM lo computó con _get_conversion_rate(C→A, date=rec.date), o sea ya usa el rate histórico (igual que      │ Solo en base con moneda extranjera, y solo pagos con         │
  │                             │ nuestro 4.b.2). Para pagos con force_amount_company_currency quedó mal (debería ser amount/force).             │ x_bkp_force_amount_company_currency                          │
  ├─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ counterpart_currency_amount │ Recalculado por el script viejo desde amount × counterpart_rate (que para B1 NULL dió amount).                 │ SÍ — recomputar después de arreglar B1 y rate                │
  ├─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ write_off_amount            │ Convertido con counterpart_rate × accounting_rate. En A=C base puede haber quedado bien por casualidad; en     │ nth (skip)                                                   │
  │                             │ foreign base puede estar mal.                                                                                  │                                                              │
  ├─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ unreconciled_amount         │ Intacto, en C con signo viejo.                                                                                 │ skip                                                         │
  └─────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

  Importante: la base all-ARS prácticamente solo necesita pasos de counterpart_currency_id + counterpart_currency_amount. La base con foreign currency necesita además los de counterpart_rate y accounting_rate
  (para los con force).

  Voy a agregar el fix como apéndice en spec_migracion.md:


Para bases que corrieron una versión anterior de los scripts (la que NO populaba
`counterpart_currency_id` y dejaba `counterpart_rate = 1.0` para los registros sin
backup), se puede aplicar el siguiente fix desde **odoo shell**.

Lo que arregla:
1. `counterpart_currency_id` (poblado para todos los pagos migrados).
2. `counterpart_rate` (recomputado para los que el ORM dejó en 1.0).
3. `accounting_rate` solo para pagos con `force_amount_company_currency`
   (los demás los computó bien el ORM usando `rec.date` → mismo resultado que 4.b.2).
4. `counterpart_currency_amount` (recomputado desde `amount × counterpart_rate`).

Lo que NO arregla (intencionalmente):
- `write_off_amount` (nice-to-have, no crítico).
- `unreconciled_amount` (sigue en company_currency con signo viejo).

Idempotente: usa el sentinel `x_bkp_migrated` para no tocar pagos creados después
del fix. Se puede correr varias veces sin daño.

```python
# Pegar en odoo shell. Asume que el módulo ya fue actualizado a 19.0.2.0.0
# con la versión vieja (rota) de los scripts.
cr = self.env.cr

# ── 0. Sentinel para no tocar pagos nuevos en re-runs ────────────────────────
cr.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'account_payment' AND column_name = 'x_bkp_migrated'
        ) THEN
            ALTER TABLE account_payment ADD COLUMN x_bkp_migrated BOOLEAN;
            UPDATE account_payment SET x_bkp_migrated = TRUE;
        END IF;
    END $$;
""")

# ── 1. accounting_rate: solo para pagos con force ────────────────────────────
# El resto ya quedó correcto via ORM compute (usa rec.date → rate histórico).
cr.execute("""
    UPDATE account_payment ap
    SET accounting_rate = ap.amount / ap.x_bkp_force_amount_company_currency
    FROM res_company rc
    WHERE rc.id = ap.company_id
      AND ap.x_bkp_migrated IS TRUE
      AND ap.currency_id != rc.currency_id
      AND ap.x_bkp_force_amount_company_currency IS NOT NULL
      AND ap.x_bkp_force_amount_company_currency != 0
      AND ap.amount IS NOT NULL
      AND ap.amount != 0;
""")

# ── 2. Caso (b) de la spec: counterpart definida pero A != C → alinear ───────
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_currency_id = ap.currency_id,
        counterpart_rate = 1.0
    FROM res_company rc
    WHERE rc.id = ap.company_id
      AND ap.x_bkp_migrated IS TRUE
      AND ap.currency_id != rc.currency_id
      AND ap.counterpart_currency_id IS NOT NULL
      AND ap.counterpart_currency_id != ap.currency_id;
""")

# ── 3. counterpart_currency_id: poblar NULLs ─────────────────────────────────
# 3.1) Transferencias internas → moneda del diario destino
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_currency_id = COALESCE(dj.currency_id, rc.currency_id)
    FROM account_journal dj
    JOIN res_company rc ON rc.id = dj.company_id
    WHERE ap.is_internal_transfer IS TRUE
      AND ap.destination_journal_id = dj.id
      AND ap.x_bkp_migrated IS TRUE
      AND ap.counterpart_currency_id IS NULL;
""")

# 3.2) Cuenta con moneda forzada
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_currency_id = aa.currency_id
    FROM account_account aa, res_company rc
    WHERE ap.destination_account_id = aa.id
      AND rc.id = ap.company_id
      AND aa.currency_id IS NOT NULL
      AND aa.currency_id != rc.currency_id
      AND ap.is_internal_transfer IS NOT TRUE
      AND ap.x_bkp_migrated IS TRUE
      AND ap.counterpart_currency_id IS NULL;
""")

# 3.3) Desde to_pay_move_line_ids cuando hay una sola moneda (sin reconcile)
cr.execute("""
    WITH payment_currencies AS (
        SELECT
            rel.payment_id,
            MIN(aml.currency_id) AS min_c,
            MAX(aml.currency_id) AS max_c
        FROM account_move_line_payment_to_pay_rel rel
        JOIN account_move_line aml ON aml.id = rel.to_pay_line_id
        JOIN account_payment ap ON ap.id = rel.payment_id
        JOIN res_company rc ON rc.id = ap.company_id
        WHERE ap.counterpart_currency_id IS NULL
          AND ap.is_internal_transfer IS NOT TRUE
          AND ap.x_bkp_migrated IS TRUE
          AND rc.reconcile_on_company_currency IS NOT TRUE
        GROUP BY rel.payment_id
    )
    UPDATE account_payment ap
    SET counterpart_currency_id = pc.min_c
    FROM payment_currencies pc
    WHERE ap.id = pc.payment_id
      AND pc.min_c = pc.max_c;
""")

# 3.4) Fallback → moneda de compañía
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_currency_id = rc.currency_id
    FROM res_company rc
    WHERE ap.company_id = rc.id
      AND ap.x_bkp_migrated IS TRUE
      AND ap.counterpart_currency_id IS NULL;
""")

# ── 4. counterpart_rate: recomputar para los que el ORM dejó mal ─────────────
# Solo afectamos los que NO tenían x_bkp_counterpart_exchange_rate (los que sí
# lo tenían fueron correctamente fijados en 1/old por el script viejo).
# 4a) B1 = A → 1.0
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_rate = 1.0
    WHERE ap.x_bkp_migrated IS TRUE
      AND ap.counterpart_currency_id = ap.currency_id
      AND (ap.x_bkp_counterpart_exchange_rate IS NULL
           OR ap.x_bkp_counterpart_exchange_rate = 0);
""")

# 4b) B1 = C, A != C → 1/accounting_rate
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_rate = 1.0 / ap.accounting_rate
    FROM res_company rc
    WHERE rc.id = ap.company_id
      AND ap.x_bkp_migrated IS TRUE
      AND ap.counterpart_currency_id = rc.currency_id
      AND ap.currency_id != rc.currency_id
      AND ap.accounting_rate IS NOT NULL
      AND ap.accounting_rate != 0
      AND (ap.x_bkp_counterpart_exchange_rate IS NULL
           OR ap.x_bkp_counterpart_exchange_rate = 0);
""")

# 4c) B1 != A != C → desde res_currency_rate
cr.execute("""
    UPDATE account_payment ap
    SET counterpart_rate = COALESCE(
        (SELECT r.rate FROM res_currency_rate r
         WHERE r.currency_id = ap.counterpart_currency_id
           AND r.company_id = ap.company_id
           AND r.name <= COALESCE(ap.date, CURRENT_DATE)
         ORDER BY r.name DESC LIMIT 1)
        /
        NULLIF(
            (SELECT r.rate FROM res_currency_rate r
             WHERE r.currency_id = ap.currency_id
               AND r.company_id = ap.company_id
               AND r.name <= COALESCE(ap.date, CURRENT_DATE)
             ORDER BY r.name DESC LIMIT 1),
            0
        ),
        1.0
    )
    FROM res_company rc
    WHERE rc.id = ap.company_id
      AND ap.x_bkp_migrated IS TRUE
      AND ap.counterpart_currency_id != ap.currency_id
      AND ap.counterpart_currency_id != rc.currency_id
      AND (ap.x_bkp_counterpart_exchange_rate IS NULL
           OR ap.x_bkp_counterpart_exchange_rate = 0);
""")

# ── 5. counterpart_currency_amount: recalcular ───────────────────────────────
cr.execute("""
    UPDATE account_payment
    SET counterpart_currency_amount = CASE
        WHEN counterpart_currency_id IS NOT NULL
             AND counterpart_currency_id != currency_id
             AND counterpart_rate IS NOT NULL
             AND counterpart_rate != 0
        THEN amount * counterpart_rate
        ELSE amount
    END
    WHERE x_bkp_migrated IS TRUE;
""")

# 5b) Asegurar positivo
cr.execute("""
    UPDATE account_payment
    SET counterpart_currency_amount = ABS(counterpart_currency_amount)
    WHERE x_bkp_migrated IS TRUE
      AND counterpart_currency_amount < 0;
""")

# ── 6. Validación ────────────────────────────────────────────────────────────
cr.execute("""
    SELECT COUNT(*) FROM account_payment
    WHERE x_bkp_migrated IS TRUE
      AND state != 'draft'
      AND (accounting_rate IS NULL OR counterpart_rate IS NULL
           OR counterpart_currency_id IS NULL);
""")
print("Pagos con NULLs después del fix:", cr.fetchone()[0])

self.env.cr.commit()
print("Fix aplicado.")
```

---

## Limitaciones conocidas

- **`counterpart_currency_amount` con valor manual previo**: en el código viejo era
  `compute` sin `store=True`, por lo que **no existía columna en DB**. Si un pago tenía
  un valor "forzado" via inverse en sesión, ese valor no se preservó (se recomputa con
  `amount × counterpart_rate`). No hay backup posible.
- **`accounting_rate` sin force**: se computa desde `res_currency_rate` a la fecha del
  pago (4.b.2). Si las cotizaciones históricas fueron modificadas después del pago, el
  rate migrado puede diferir del que efectivamente se usó al postear el asiento.

---

## Nota: protección de pagos creados después de la migración

La migración usa la columna `x_bkp_migrated BOOLEAN` como sentinel:

- El pre-migrate la crea y la setea en `TRUE` para todas las filas existentes al
  momento del upgrade.
- Cada UPDATE del post-migrate (y del fix-script del apéndice) filtra por
  `x_bkp_migrated IS TRUE`.
- Pagos creados después de la migración no son fields del modelo Odoo nuevo, así
  que el ORM nunca les pone valor → quedan en `NULL`. Como `NULL = TRUE` evalúa a
  `NULL` (no `TRUE`) en SQL, esos pagos quedan automáticamente excluidos de los
  scripts.

### Queries de validación

Para verificar después del upgrade que la protección está activa:

```sql
-- 1) Total de filas marcadas como migradas (debe coincidir con el total al momento del upgrade)
SELECT COUNT(*) FROM account_payment WHERE x_bkp_migrated IS TRUE;

-- 2) Filas con NULL: deberían ser exclusivamente pagos creados POST-migración
SELECT COUNT(*), MIN(create_date), MAX(create_date)
FROM account_payment
WHERE x_bkp_migrated IS NULL;

-- 3) Inconsistencia: ninguna fila con backup poblado debería tener x_bkp_migrated NULL
--    (debe dar 0)
SELECT COUNT(*) FROM account_payment
WHERE x_bkp_migrated IS NULL
  AND (x_bkp_counterpart_exchange_rate IS NOT NULL
       OR x_bkp_force_amount_company_currency IS NOT NULL
       OR x_bkp_write_off_amount IS NOT NULL
       OR x_bkp_unreconciled_amount IS NOT NULL);

-- 4) Prueba activa: crear un pago nuevo y verificar que quedó NULL
SELECT id, name, x_bkp_migrated, create_date
FROM account_payment
ORDER BY id DESC LIMIT 5;
```

### Columnas de backup que quedan en la DB

Después de la migración persisten estas columnas SQL (no son fields de Odoo, no
afectan al ORM):

| Columna | Para qué se usa post-migración |
|---|---|
| `x_bkp_migrated` | Sentinel de exclusión de pagos nuevos |
| `x_bkp_counterpart_exchange_rate` | Source para fix re-runs de `counterpart_rate` |
| `x_bkp_force_amount_company_currency` | Source para fix re-runs de `accounting_rate` |
| `x_bkp_write_off_amount` | Source para re-runs del recompute de `write_off_amount` |
| `x_bkp_unreconciled_amount` | Source para re-runs del recompute de `unreconciled_amount` |

Quedan indefinidamente. Si en el futuro se decide eliminarlas (limpieza tras un
período de gracia), un script `ALTER TABLE account_payment DROP COLUMN x_bkp_*`
es suficiente. **No conviene removerlas mientras siga existiendo la posibilidad
de necesitar un fix-script adicional.**
