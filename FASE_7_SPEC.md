# FASE 7 — Planes, capacidades, limpieza dirigida y motor profesional

> Documento de referencia de lo construido en la versión 0.8.0 y de las decisiones
> tomadas. El prompt original de la Fase 7 se adaptó al estado real del repo
> (que ya traía la microfase 6.2: `capabilities.py`, `/clean/download` y la
> migración `0007` ocupada). Detalle de cambios: [`CHANGELOG.md`](./CHANGELOG.md).

## 0. Principio rector (cumplido)

Toda la arquitectura de planes y capacidades quedó **construida y cableada**, con el
interruptor global `PLAN_ENFORCEMENT` (backend `Settings`) + `VITE_PLAN_ENFORCEMENT`
(frontend) **en `false`**: todo accesible para probar, cada puerta con su cerradura
instalada. Encenderlo no requiere tocar componentes. Nada de IA generativa nueva se
activó: las dos costuras (`interpret_cleaning_instructions` y `refine_with_ai`)
tienen interfaz final y un único `# TODO IA` cada una.

## 1. Matriz de planes (fuente única de verdad)

Backend: `api/app/capabilities.py` (se extendió el módulo existente en vez de crear
`plans.py`, para no duplicar la fuente de verdad de la microfase 6.2).
Frontend: `frontend/src/lib/plans.ts` (misma matriz + `useCapability` en
`lib/usePlan.ts`).

| Capacidad | Básico | Analista | Gold (construcción) |
|---|---|---|---|
| Estandarizar + limpiar (reglas por defecto) | ✅ | ✅ | ✅ |
| Dashboard / Explorar / Alertas / Historial | ✅ | ✅ | ✅ |
| Asistente IA (panel derecho, insights) | ✅ limitado (20/mes) | ✅ (200/mes) | ✅ |
| Descargar base limpia | ❌ | ✅ | ✅ |
| Descargar reportes (PDF/Excel) | ❌ | ✅ | ✅ |
| Chat de limpieza dirigida (2/mes + tokens) | ❌ | ✅ | ✅ |
| Conectar bases SQL | ❌ | ❌ | 🚧 |
| Acceso a comunidad | ❌ | ❌ | 🚧 |

## 2. Base de datos

- **`0008_plans.sql`**: check de `profiles.plan` → `('basico','analista','gold')`;
  migra los `gold` legacy a `analista`; `profiles.is_admin`; fix del rol `costo` en
  `dataset_columns`; policy + grant de update para el mapeo editable (§5.10).
- **`0009_cleaning_credits.sql`**: `ai_usage.kind` acepta `'cleaning'`; **ledger**
  `plan_addons` (positivos = otorgados, negativos = consumos del sistema; saldo =
  suma); `addon_requests` (pendiente|atendida); RLS de lectura propia; escrituras
  solo service_role; grants patrón 0007.
- *Nota de numeración*: el prompt original decía 0007/0008, pero `0007` ya estaba
  ocupada por `public_table_grants` → se usaron 0008/0009.

## 3. Backend

- `require_capability_for_user` respeta `PLAN_ENFORCEMENT` (apagado → deja pasar sin
  red). `get_is_admin`, `min_plan_for` y `display_plan` con los 3 planes.
- `quota.py`: cupos **separados por `kind`** — insights (summary/chat/recommendation)
  vs limpieza (`cleaning`). `check_cleaning_quota` (base `AI_CLEANING_MONTHLY_LIMIT=2`
  + saldo addons; 429 con CTA a Planes), `record_cleaning_usage` (descuenta el token
  con una fila negativa del ledger cuando se excede la base). Fail-open documentado.
- **`POST /clean/assisted`**: capacidad → cupo → interpretar → correr → registrar.
  Instrucciones no reconocidas → **422 sin consumir el intento**. Respuesta =
  `CleanResult` + bloque `dirigida` (columnas incluir/excluir, reglas forzadas,
  avisos, cupo restante).
- **`GET /plans/usage`**, **`POST /addons/request`**, **`POST /admin/grant-credits`**
  (solo `is_admin`; alternativa SQL en el README) en `api/app/routes/plans.py`.
- `/clean`, `/clean/download` y `/metrics` aceptan `mapping` (roles corregidos);
  `/clean/download` acepta además `scope` para descargar el resultado dirigido.

## 4. Frontend

- **Sidebar**: ítem **Planes** (`/planes`, ícono CreditCard) antes de Configuración.
- **`Planes.tsx`**: 3 tarjetas desde la matriz (Gold con badge "En construcción",
  SQL + comunidad), CTA de solicitud de plan, y sección **"Tokens de limpieza
  dirigida (addons)"** con cupo del mes, saldo y **"Solicitar más"** →
  `POST /addons/request` con confirmación ("nos pondremos en contacto").
- **`AiPanel` relocalizado**: fuera del `AppShell` global; se renderiza **solo en
  `/` (Resumen) y `/explorar`** (condicional por ruta). El resto usa todo el ancho.
- **`Limpieza.tsx`**: botón superior **"Limpiar datos"** (reglas por defecto, todos
  los planes) + **chat horizontal inferior** habilitado para Analista/Gold (con
  enforcement apagado, visible con su badge) + botón **"Limpiar con mis variables"**
  → `/clean/assisted`. **Advertencia visible**: "Tienes 2 intentos al mes… agrega
  tokens en Planes" con intentos restantes; agotados → deshabilitado con CTA.
  Tarjeta de **mapeo de columnas** editable (§5.10). Avisos del motor visibles.
- **Gating de descargas**: Reportes y "descargar base limpia" muestran candado + CTA
  "Mejora a Analista" cuando el enforcement esté encendido; apagado, todo descarga.
- **Configuración**: contador de limpieza dirigida + tokens, enlace a Planes.

## 5. Motor de datos — mejoras profesionales implementadas

1. ✅ Nulos numéricos **nunca** imputados con 0 (preservados como NaN, catalogados,
   marcados en la descarga). Política visible por columna en el reporte de calidad.
2. ✅ Duplicados: detección por fila completa normalizada con **criterio explícito**
   y **advertencia** cuando no hay columna identificadora. *Decisión justificada*:
   se eligió la alternativa "advertir" del spec por sobre la clave de negocio
   parcial (fecha+cliente+producto+monto), porque una clave parcial eliminaría MÁS
   ventas legítimamente idénticas, no menos.
3. ✅ Outliers IQR solo en roles métricos (monto/costo/cantidad); nunca IDs/RUT/años.
4. ✅ Detección de tipo con muestra **aleatoria determinista** (semilla fija) y
   **confianza por columna** reportada.
5. ✅ Convención numérica ("850.000") decidida por **consistencia de la columna**.
6. ✅ Fechas: `dayfirst` **dominante por columna** + meses en texto ("01 mayo 2026").
7. ✅ **Caché del pipeline** por hash de contenido + reglas + mapeo + alcance
   (LRU 4, tope 1,5M celdas): cambiar el periodo no re-corre el motor.
8. ✅ Nulos vectorizados y parseos por columna calculados una vez por fase.
9. ✅ **Reporte de calidad por columna** (`reporte_calidad`): rol, tipo+confianza,
   nulos y %, inválidos, outliers, convención — insumo del refinado IA.
10. ✅ **Mapeo editable en la UI** con persistencia best-effort en `dataset_columns`
    y efecto en toda la app (limpieza, métricas, descargas).
11. ✅ **Fuzzy matching** Levenshtein acotado ("Santigo"→"Santiago") con guardas.
12. ✅ `loader.py`: **multi-hoja** (elige la hoja con datos, avisa las omitidas),
    **fila de título** detectada y omitida, separador CSV por consistencia.
13. ✅ Costuras IA: `refine_with_ai` (flag `AI_REFINE_ENABLED`, apagado) e
    `interpret_cleaning_instructions` (determinista) — un `# TODO IA` cada una.

## 6. Verificación

- **57 tests** de API en verde (`python -m pytest tests/`): 33 previos + 24 nuevos
  (matriz y enforcement, cupo de limpieza 429/addons, `/clean/assisted`
  dirigido/negaciones/422 sin consumo/429, `/plans/usage`, `/addons/request`,
  `/admin/grant-credits` 403, nulos monetarios ≠ 0, outliers vs ID, meses en texto,
  convención decimal/miles, fuzzy, multi-hoja + título, aviso de dedup, mapping
  corregido, caché).
- **`npm run build` verde** (tsc + vite).
- E2E Playwright: pendiente (el repo no trae infraestructura Playwright; queda en
  PHASE_STATUS → Pendiente).

## 7. Decisiones tomadas (respuestas al §7 del prompt)

1. **Nombre del tercer plan**: **Gold** (según lo pedido; renombrable en la matriz).
2. **Créditos**: los **2/mes se reinician** cada mes; los **addons son saldo
   consumible aparte** que no expira (la recomendación) — implementado como ledger.
3. **Otorgar tokens**: **endpoint admin** `/admin/grant-credits` con
   `profiles.is_admin` + alternativa SQL documentada en el README.
4. **Comunidad (Gold)**: marcada "En construcción" en la tarjeta; el destino
   (Discord/Circle/in-app) se decide al construirla.
5. **Confirmado**: Básico **sí** estandariza y limpia (no descarga); el `AiPanel`
   vive solo en Resumen y Explorar datos.
