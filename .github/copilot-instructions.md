
# 🧠 Instrucciones optimizadas para Copilot – Revisión de código Odoo (v19.0)

## Contexto
- El repositorio contiene **módulos Odoo** compatibles con la versión **v19.0** (o versiones compatibles cercanas).
- El objetivo es **revisar cambios de código** y **sugerir mejoras seguras y relevantes**, sin hacer revisiones excesivamente estrictas.

---

## 🔍 Reglas generales

1. **Responder siempre en español.**
2. Detectar y corregir **errores de tipeo u ortografía evidentes** en nombres de variables, métodos o comentarios (cuando sean claros).  
3. No sugerir traducciones de docstrings o comentarios entre idiomas (no proponer pasar del inglés al español o viceversa).  
4. No proponer agregar docstrings si el método no tiene uno.  
   - Si ya existe un docstring, puede sugerirse un estilo básico acorde a PEP8, pero **no será un error** si faltan `return`, tipos o parámetros documentados.  
5. No proponer cambios puramente estéticos (espacios, comillas simples vs dobles, orden de imports, etc.).

---

## 🧩 Revisión de modelos (`models/*.py`)

- Verificar que:
  - Los campos (`fields.*`) tengan nombres claros, consistentes y no entren en conflicto con otros módulos.
  - Las relaciones (`Many2one`, `One2many`, `Many2many`) estén bien definidas y referencien modelos válidos.
  - Las constraints declaradas con `_sql_constraints` o `@api.constrains` mantengan la integridad esperada.
- Sugerir uso de `@api.depends` si un campo compute carece de dependencias explícitas.
- Si se redefine un método de Odoo, asegurar que se llama correctamente `super()`, manteniendo el contrato original.
- Si hay lógica nueva, evitar loops costosos con búsquedas dentro de iteraciones; sugerir `mapped`, `filtered` u otras formas más eficientes.

---

## 🧾 Revisión del manifest (`__manifest__.py`)

- Confirmar que todos los archivos usados (vistas, seguridad, datos) estén referenciados en el manifest.
- Si se agregan o modifican modelos, vistas o datos nuevos, sugerir incrementar la versión del módulo (por ejemplo: `version: “1.0.0” → “1.0.1”).
- Verificar dependencias declaradas: que no falten módulos requeridos ni se declaren innecesarios.

---

## 🪶 Revisión de vistas XML (`views/*.xml`)

- Confirmar que uses herencias (`inherit_id`, `xpath`) efectivamente, no redefiniciones completas innecesarias.
- Validar que los campos referenciados en la vista existan en los modelos correspondientes.
- Atento a cambios en las versiones nuevas de Odoo:
  - En Odoo 18, el elemento `<tree>` fue reemplazado por `<list>` en vistas de tipo lista.
  - Odoo 18 ha simplificado atributos condicionales: `attrs` o `states` pueden ser reemplazados por condiciones directas (`invisible="..."`, `readonly="..."`)
- Sugerir no duplicar vistas ni redefinir todo el `arch` si puede hacerse con un `xpath`.

---

## 🔒 Seguridad y acceso

- Verificar los archivos `ir.model.access.csv` para nuevos modelos: deben tener permisos mínimos necesarios.
- Revisar reglas (`ir.rule`): que no otorguen accesos innecesarios (especialmente `write`, `unlink`).
- No proponer abrir acceso global sin justificación.

---

## ✅ Checklist rápida para el review

| Categoría | Qué comprobar Copilot |
|---------|--------------------------|
| Modelos | Relaciones válidas; constraints; uso adecuado de `@api.depends`; `super()` correcto |
| Vistas XML | Herencias correctas; campos válidos; adaptación a cambios de versión (p.ej. `<list>` vs `<tree>`) |
| Manifest | Archivos referenciados; versión del módulo incrementada si hay cambios relevantes |
| Seguridad | Accesos mínimos necesarios; reglas revisadas |
| Rendimiento / ORM | Evitar loops costosos; no SQL innecesario; aprovechar mejoras de la versión v19.0 |
| Ortografía & typos | Errores evidentes corregibles sin modificar idioma ni estilo |

---

## 💡 Estilo del feedback

- Ser breve, claro y útil:  
  👉 “El campo `partner_id` no se encuentra referenciado en la vista.”  
  👉 “Este método redefine `write()` sin usar `super()`.”  
  👉 “En v19.0, `<tree>` ya no se usa; reemplazar por `<list>`.”  
  👉 “Tip: hay un error ortográfico en el nombre del parámetro.”  
- Evitar explicaciones largas o reescrituras completas salvo que el cambio sea claro y necesario.
