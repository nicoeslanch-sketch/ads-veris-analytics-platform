# Estado del proyecto por fases — ADS Veris

**Estado actual: Fases 0 a 18 completas en código.**
La Fase 18 (`CHANGELOG` [0.21.0]) audita la plataforma contra la Prueba de
Estrés Multihoja (todos los KPI reproducidos de forma independiente) y corrige
lo encontrado: convención de `"1,234"` por magnitud de la columna, canónicos
estables entre hojas (TipoCliente), grupos sin etiqueta "nan", filtro mensual
consistente y conflictos de ID sin falsos positivos de claves foráneas. Además
lleva gráficos a TODOS los resúmenes adaptativos (inventario y campañas por
sucursal/plataforma; clientes, sucursales, trabajadores y metas con
distribuciones), agrega "Ventas por {columna}" flexibles (sucursal, región,
zona… incluidas columnas enriquecidas al relacionar hojas), amplía la
cobertura de negocio de Observaciones en la exportación, hace legibles las
hojas exportadas y aclara la Limpieza (franja de acción en navy, botón mayor,
preguntas de mapeo solo con columnas candidatas). El parche `0.21.1` permite
revisar y repetir una limpieza sin resubir el archivo, simplifica la relación
automática de ventas con costos y corrige conteos auditables de columnas
completas. El parche `0.21.2` valida el libro avanzado multihoja: unifica la
escala de porcentajes, elimina falsos conflictos de ID y reconoce maestras de
costos con fecha de vigencia para relacionarlas por SKU. También persiste la
selección recomendada para que una recarga no reactive hojas auxiliares. Motor
`0.21.2`; la última migración sigue siendo **0021**.

**Historial de Fase 17.**
La Fase 17 (`CHANGELOG` [0.20.0]) simplifica el mapeo Básico y completa el
procesamiento, limpieza, análisis, exportación y restauración multihoja. Las
relaciones solo permiten one-to-one/many-to-one confirmadas y demuestran que
filas y totales no cambian. Requiere aplicar **0021** antes de desplegar el
backend; esta rama no ejecuta migraciones, merge ni despliegues.

**Historial de Fase 16.**
La Fase 16 (`CHANGELOG` [0.19.0]) cierra la pérdida contextual de literales,
bloquea globalmente cálculos con monedas incompatibles, reemplaza snapshots v2
por restauración multihoja v3 con revisión reservada y RPC atómica, compara la
calidad antes/después con la misma fórmula y entrega exportaciones auditables.
También migra el E2E manual a `@playwright/test` e incorpora comprobaciones
directas de RLS y Storage. Operativo: aplicar **0019** y **0020** en staging,
ejecutar el smoke estricto con dos usuarios y solo después promover a producción.
Resultado local verificado: **323 Pytest, 31 Vitest, build y Playwright 3/3**.
Detalle y riesgos: `docs/FASE_16_AUDITORIA.md`.

**Historial de Fase 15.**
La Fase 15 (`CHANGELOG` [0.18.0], "todo en 10") corrige los bugs P0
verificados del plan externo (upgrade_basico degradado a 'otro', literales
nan/None borrados por el loader, KPI de planes del admin, monedas mixtas
sumadas → ahora BLOQUEAN los KPIs, doble fuente de RUT unificada en
billing_identities, errores técnicos de Supabase en recuperación), sube la
exactitud (líderes brutos antes del recorte a 12, fusiones de ENTIDADES
comerciales solo como sugerencia, calidad multidimensional de 6 componentes)
y endurece la operación: snapshots v2 con versión del motor y guardia
monotónica, arranque fail-closed con APP_ENV=production, GET /version para
verificar despliegues, test de paridad de la matriz de planes TS↔Python,
límite de ráfaga de IA, job de seguridad en CI (pip-audit + npm audit),
runbook `docs/OPERACION.md`, `scripts/smoke_rls.py` de aislamiento entre
clientes y E2E versionado (`npm run test:e2e`). Operativo: ejecutar la
migración **0019** y setear **APP_ENV=production** en Render.
**Backend 309 tests + Vitest + build + E2E.**

**Historial 0.17.x (estabilización previa): Fases 0 a 14 + 0.17.5.**
La versión 0.17.5 reemplaza las filas acopladas del Resumen por columnas
independientes y elimina los espacios verticales artificiales sin volver a
estirar tarjetas; el orden móvil se conserva.
La versión 0.17.4 elimina la carrera entre el selector de archivos y la
revalidación de acceso, sin relajar el control fail-closed, y alinea toda la
experiencia administrativa: etiqueta de acceso total, capacidades y cuotas IA
ilimitadas. La migración `0018` mantiene el rol de
`servicios@adsveris.com` aunque la cuenta se cree o actualice después.
**Backend 279 tests + Vitest 21 + build de producción.**
La versión 0.17.3 completa el circuito de recuperación: correo con redirect
autorizado, panel público para ingresar y confirmar la nueva contraseña,
política compartida de 8 caracteres con letras y números, compatibilidad con
enlaces antiguos, cierre de la sesión temporal y retorno al login.
**Vitest 21 + build de producción.**
La Fase 14c (`CHANGELOG` [0.17.2]) cierra el bypass de upgrades sin identidad
en el backend, usa Supabase Auth como señal autoritativa de correo confirmado,
separa los rate limits, corrige concentración bruta sin romper el orden neto de
las tablas, elimina el fallback del mes parcial en Resumen, cierra capacidades
stale durante refrescos y muestra al administrador únicamente el RUT enmascarado.
La migración `0017` permite desvincular identidades con `ON DELETE SET NULL`.
**Backend 276 tests + Vitest 15 + build de producción.**
La Fase 14b (`CHANGELOG` [0.17.1]) cierra los 4 P0 del informe externo sobre
la Fase 14 — todos verificados como reales: elegibilidad del trial en API y
RPC (un plan pagado/admin ya no reserva el RUT de otra empresa), reversa de
la identidad cuando la activación falla (minimización de datos), RUT
obligatorio al contratar (solicitud vinculada a `billing_identity_id`) y la
demo SIN escrituras (el guardar análisis ficticio quedaba en Supabase). Más:
Explorar respeta meses parciales y utilidad desconocida (null, no $0),
participación BRUTA que suma 100% para toda afirmación de concentración,
copy de parcialidad sin causa inventada, AccessProvider sin fuga entre
cuentas, rate limit también por RUT, modales accesibles (Escape/reset/foco)
y pruebas de verdad: gates por HTTP real (Anthropic/motor/restore NO corren
en 403), Vitest estrenado con paridad TS↔Python del RUT.
**Backend 269 tests + Vitest 12 + build + E2E 21/21.** Migración `0016`
actualizada: RE-ejecutarla en Supabase (es re-ejecutable).
La Fase 14 (`CHANGELOG` [0.17.0]) cierra los CUATRO bypasses comerciales
(gates en `/ai/*` — el más caro, con métricas enviadas por el cliente —,
`/metrics`, `/restore/latest` y el orden del conector Sheets; cuota `sin_plan`
= 0 explícito, antes 500), unifica el acceso en `GET /me/access` (capacidades
efectivas del SERVIDOR; el frontend ya no arranca optimista), e introduce la
**prueba gratuita de 15 días con RUT** (migración **0016**: RPC atómica
`activate_account_trial` solo service_role, unique absoluto por usuario +
índice único PARCIAL por RUT sobre `revoked_at is null`, `can_process_data()`
con políticas `AS RESTRICTIVE` en datasets/Storage, fechas del servidor sin
cron), la **demo ficticia regenerable** ("Comercial Andes SpA": snapshots
nacidos del motor real con test de contrato, provider aislado que jamás toca
el DatasetContext), la **interceptación de carga en las tres puertas** (picker,
drag & drop, Sheets — modal comercial antes de cualquier byte), la
**parcialidad POR MES** en la evolución (proyección/Alertas/IA/gráfico dejan
de leer un mes a medio llenar como caída) y el **registro reforzado accesible**
(confirmar contraseña con aria-live, ojos con aria-label, pegar permitido).
Recordatorio operativo: ejecutar la migración `0016` y configurar la política
de contraseñas en Supabase → Authentication (README §Supabase).
**252 tests + build + E2E 19/19.**

La Fase 13 (`CHANGELOG` [0.16.0]) introduce el modelo de cuentas nuevas SIN
plan (migración **0015**: navegar sí, subir archivos no — panel con CTA a
Planes; las cuentas existentes conservan su plan), contraseña reforzada en el
registro (8+ caracteres, letras y números), y corrige el triage verificado del
tercer informe externo MÁS dos hallazgos propios: las fechas ISO de Excel se
VOLTEABAN (1 de mayo → 5 de enero: la evolución mensual de la base real
mostraba 12 meses donde solo hay dos) y una clave pegada de StrictMode que
impedía que Explorar se adaptara al archivo. **224 tests + build + 2 E2E.**
La reapertura del último trabajo ya no reconstruye pandas en cada inicio: la
API recupera un snapshot versionado con estandarización, limpieza y métricas en
una sola llamada. Cuando no existe, lo calcula una vez y lo deja listo para las
siguientes aperturas. La migración `0014` restringe su escritura al backend.
La Fase 12b (`CHANGELOG` [0.15.0]) corrige los P0 confirmados del informe: los
valores no interpretables se CONSERVAN (la calidad ya no "mejora" destruyendo
evidencia), "1,234" se decide por evidencia de columna con aviso, el margen
mensual usa denominador pareado desde el backend, y se reparó un cuelgue real
de StrictMode que dejaba Limpieza/Resumen/Explorar/IA en spinner eterno.
Además: "Registros" en vez de "Transacciones", devoluciones visibles (ingresos
netos), tarjeta Cobertura de Costos (reemplaza el "Resultado del Periodo"
duplicado), cobertura por grupo con umbral para recomendaciones de
rentabilidad, hasta 12 productos, extrapolación etiquetada, mes en curso
marcado parcial, columnas vacías detectar-sin-eliminar, protección de filas
"Total X" legítimas, límites de columnas/celdas y alertas revisadas por
dataset. **202 tests + build + E2E.**

Pendientes del informe (rechazados/postergados con razón — ver [0.15.0]):
bloqueo de KPIs con monedas mixtas, puntaje de calidad multidimensional,
fuzzy de clientes/productos como sugerencia, auditoría CSV en ZIP,
severidades estructuradas, streaming del export grande, semáforo de
concurrencia, score combinado de mapeo, pruebas frontend (Vitest).
El motor ahora detecta duplicados siempre y conserva todas las filas por defecto.
Solo una confirmación explícita permite eliminar repeticiones exactas del archivo
original; las coincidencias creadas por la normalización nunca se borran. La
decisión se propaga a métricas, descarga, IA, caché e historial, y las incidencias
usan la fila física del archivo como trazabilidad. Las migraciones `0012` y
`0013` persisten esa opción y la saga recuperable de eliminación. El Bloque 2
corrige el doble conteo textual, elimina el total engañoso
de problemas y separa montos cero, negativos e IQR sin modificar valores. El
Bloque 3 distingue vacíos físicos, placeholders por rol y posibles patrones
estructurales, además de reparar mojibake únicamente con conversiones strict y
auditoría completa.
El Bloque 4 añade diagnósticos no destructivos de coherencia nombre↔ID y una
auditoría de fórmulas Excel limitada a las filas reales de datos, con especial
atención a fórmulas volátiles y fórmulas presentes en identificadores.
El Bloque 5 procesa hojas bajo demanda y usa un manifiesto de sesión explícito
para la descarga completa; el caché nunca funciona como fuente de verdad.
El cierre de rendimiento comparte carga/estandarización/limpieza entre módulos,
acelera Excel sin fórmulas, invalida el caché de Storage al eliminar y divide el
frontend por rutas. En la base REQ5325 (14.917×16), el flujo frío completo midió
9,4 s y los pasos repetidos quedaron entre 2 ms y ~0,5 s según la etapa.
La auditoría posterior del dashboard corrigió márgenes por grupo con costos
parciales, reconcilió gastos mensuales, exige montos legibles para habilitar el
dashboard y conserva encabezados Excel repetidos. También añadió concentración
de clientes, clientes únicos y ventas por día de la semana sin debilitar las
reglas no destructivas, multihoja ni la trazabilidad de la Fase 12.

La Fase 11 ataca la lentitud con bases grandes (>50.000 filas) en su causa raíz:
el caché del pipeline excluía los archivos grandes y cada módulo reprocesaba
todo — ahora el caché funciona por **presupuesto de celdas con desalojo LRU** y
el parseo es **por valores únicos** (50.000×8: de ~13,3 s a ~1,8 s; módulos
siguientes ~0,3 s). "Retomar" ya no descarga el archivo al navegador. El motor
gana precisión: números US (`1,234.56`), fechas mixtas DD/MM–MM/DD resueltas
por evidencia por valor con aviso, variantes morfológicas (pagada→pagado) con
guardas conservadoras, y el mapeo parcial del usuario se FUSIONA con el
automático (corregir una columna ya no vacía el dashboard). El frontend suma
timeouts con botón "Reintentar", claves de recálculo con mapeo/hoja, moneda
activa real (US$/€/$) y continuidad de sesión: al iniciar sesión se restaura el
último trabajo, con "Estandarizar nuevo documento" explícito y contactos
directos (WhatsApp, Instagram, servicios@adsveris.com) en la ayuda.
La Fase 10 es el endurecimiento comercial tras el triage crítico del informe de
calidad externo: cierra la **vulnerabilidad P0 de profiles** (migración 0011 —
un usuario podía auto-asignarse Gold/admin vía REST), corrige la **exactitud
financiera** (cobertura de costos, Utilidad Bruta/Resultado del Periodo en vez
de nombres que prometían de más, moneda detectada con advertencia de mezcla,
"vs mes anterior" calendario real, Alertas/Reportes sin heredar el mes del
Resumen), hace el **motor más conservador** (fuzzy jamás en identificadores,
duplicados sin ID solo exactos, scope vacío = 422, export con hoja de
Observaciones sin contaminar datos, .xls rechazado claro, guardia anti
ZIP-bomb, selector de hoja, diccionario auditado), y deja la app **responsive**
(sidebar hamburguesa, asistente IA en drawer móvil sin consumo oculto de cupo,
recuperar contraseña). Deps fijadas + CI en GitHub Actions.

La Fase 8 enciende el modelo comercial (`PLAN_ENFORCEMENT` ON: base limpia y limpieza
dirigida = Analista+, con aviso "Necesitas el Plan X → Ir a comprar el plan"), agrega el
**panel Administrar cuentas** para la cuenta administradora (`servicios@adsveris.com`):
todas las cuentas con semáforo de solicitudes, activación manual de planes (costura
lista para la pasarela de pago) y bandeja de soporte del botón "¿Necesitas ayuda?".
Además: retención de archivos por plan en Storage, cupos de limpieza dirigida 10/25 por
mes, Explorar/Resumen adaptativos a las columnas reales del archivo, motor con monedas/
porcentajes/negativos contables y filas de totales excluidas, y una capa de color suave
en toda la UI. Las costuras de IA generativa siguen preparadas y APAGADAS.

> Referencia rápida de qué está construido y qué viene. La especificación
> completa vive en [`SPEC.md`](./SPEC.md).

## ✅ Fase 0 — Scaffold + marca + shell (completa)

**Frontend** (`frontend/` — Vite + React + TypeScript + Tailwind v4):
- Tokens exactos de marca (navy `#1a3a52`, navy-deep, teal, gold, green, coral) y Poppins 400–800 autoalojada.
- Layout principal: sidebar navy con 9 secciones + "Fuentes conectadas" + bloque de ayuda; topbar con selector de rango de fechas (es-CL), campana y menú de perfil con logout; panel derecho **Asistente IA inactivo** ("se activa cuando cargas tus datos").
- Login/registro con Supabase (email + contraseña, metadata de nombre y empresa) y **rutas protegidas** (sin sesión → `/login`).
- 9 páginas con estados vacíos coherentes con la regla no negociable: *sin datos, no hay dashboard*.

**Base de datos** (`supabase/migrations/0001_profiles.sql`):
- Tabla `profiles` (empresa, RUT, plan `basico|gold`, preferencias es-CL) con RLS y trigger de creación automática al registrarse.

**API** (`api/` — FastAPI):
- `/health` público; validación de JWT de Supabase (firma HS256, expiración, audiencia) en todo lo demás.

## ✅ Fase 1 — Pipeline de datos (completa)

**API** (`api/app/engine/` + `api/app/routes/pipeline.py`):
- `POST /standardize` — unifica textos duplicados (mayúsculas/tildes/espacios), estandariza fechas a DD/MM/YYYY y números con formato chileno ($ y punto de miles); detecta tipos por columna y mapea columnas al esquema del negocio (fecha, cliente, producto, categoría, monto, cantidad, canal, sucursal, vendedor). Devuelve preview antes/después + resumen de cambios.
- `POST /clean` — detecta duplicados, valores nulos, fechas inválidas, textos inconsistentes, tipos incorrectos, columnas vacías y valores fuera de rango (outliers IQR). Con `apply=true` corrige según las reglas activas; con `apply=false` solo reporta (vista previa con celdas problemáticas marcadas). Devuelve calidad % antes/después.
- `POST /metrics` — indicadores básicos del dataset limpio: ingresos totales, ticket promedio, evolución mensual, por categoría/canal/sucursal, top 5 productos.
- **Todos los endpoints exigen JWT de Supabase.** Entrada por multipart (archivos pequeños, máx. 15 MB) o por `storage_path` (la API descarga desde **Supabase Storage** con la service_role key — flujo preferido en producción).
- Tests: `api/tests/` (pytest, 10 pruebas) con datos de ejemplo `api/tests/data/ventas_ejemplo.csv`.

**Base de datos** (`supabase/migrations/0002_datasets_pipeline.sql`):
- `datasets` (archivos cargados: nombre, storage_path, filas, columnas, estado, calidad %), `dataset_columns` (mapeo de columnas), `cleaning_jobs` (reglas, problemas, antes/después), `activity_log` (historial básico). Todo con RLS por usuario.
- Bucket privado `datasets` en Storage con políticas por carpeta de usuario.

**Frontend**:
- Cliente API (`src/lib/api.ts`) que adjunta el JWT de la sesión Supabase; `DatasetContext` comparte el dataset de la sesión entre módulos.
- **Estandarización**: zona de carga (drag & drop + botón), "¿Qué hace?", proceso en 3 pasos, tabla de archivos recientes con estado, nota de seguridad. Llama a `/standardize`.
- **Limpieza de datos**: tarjetas de estado (archivo, filas, columnas, anillo de calidad %, estado), pasos de limpieza, vista previa "antes de la limpieza" con errores resaltados, problemas detectados, "qué se corregirá", reglas activas con toggles, tarjeta premium (Gold), botón **"Aplicar limpieza y continuar"**. Llama a `/clean` (detectar y aplicar).
- Persistencia best-effort en Supabase (Storage + `datasets` + `cleaning_jobs` + `activity_log`); si Supabase no está configurado, el pipeline funciona igual en memoria.
- "Fuentes conectadas" del sidebar refleja el archivo cargado (punto dorado = pendiente, verde = limpio).

## ✅ Fase 2 — Resumen / dashboard (completa)

**API** (`api/app/engine/metrics.py`):
- `POST /metrics` ampliado: KPIs con **variación vs el periodo anterior equivalente** (Ingresos, Gastos, Ganancia Neta, Margen, Flujo de Caja operacional — estos últimos solo si el archivo trae columna de costo), evolución mensual de ingresos/gastos/utilidad, análisis por categoría con utilidad y margen, ventas por canal/sucursal, top 5 productos y **proyección a 3 meses** (crecimiento promedio mensual acotado).
- Filtro de periodo con `date_from`/`date_to`; la evolución mensual siempre muestra el periodo completo como contexto.
- Ratios de balance (ROA, ROE, liquidez corriente, prueba ácida, rotación de inventario, días de cobro/pago) **declarados pero sin valor**: requieren datos de balance que se conectarán en fases posteriores — la UI los muestra con "—" y la nota explicativa.
- CSV de ejemplo ampliado a 3 meses (abril–junio) con columna `Costo`.

**Frontend** (`frontend/src/pages/Resumen.tsx`):
- Dashboard según maqueta: 4 tarjetas KPI con variación y sparkline, gráfico "Evolución de Ingresos, Gastos y Utilidad" (Recharts), Indicadores Clave, tabla "Análisis por Categoría" con barras de margen, "Estado Financiero" con semáforo de Salud Financiera (según margen), donut "Ventas por Canal/Sucursal" con total al centro, "Top Productos / Servicios" y "Proyección (Próximos 3 meses)".
- **Selector de rango de fechas del topbar funcional**: filtra todo el dashboard ("Todo el periodo" + cada mes con datos); al entrar se auto-selecciona el último mes.
- Paleta de series validada (contraste ≥3:1, separación para daltonismo): pasos de las rampas de marca; el navy queda para texto/UI.
- La regla no negociable se mantiene: sin dataset limpio, el Resumen muestra el estado vacío con CTA a Estandarización.

## ✅ Fase 3 — Asistente IA (completa)

**API** (`api/app/routes/ai.py`):
- `POST /ai/summary` — resumen ejecutivo automático + 4 preguntas sugeridas a partir de las
  métricas del dashboard. `POST /ai/chat` — chat anclado a los datos con streaming (SSE).
- Las llamadas a la **Anthropic API ocurren solo en el backend** (`ANTHROPIC_API_KEY` vive en
  Render); modelo configurable con `ANTHROPIC_MODEL`. Sin key configurada responde **503 con
  mensaje claro** (nunca un 500 opaco).
- **JWT de Supabase moderno**: además del HS256 legacy, la API valida tokens ES256/RS256 vía
  JWKS (`/auth/v1/.well-known/jwks.json`), con caché de claves de 5 minutos.

**Frontend** (`frontend/src/components/layout/AiPanel.tsx`):
- Panel derecho activo: bloqueado sin datos → cargando (métricas + resumen) → activo con
  resumen del periodo, preguntas sugeridas clickeables, historial de chat e input con
  respuesta en streaming. Botón de reintento ante errores.
- Pendiente para Fase 5: gating por plan y contador de consultas (SPEC §9).

## ✅ Fase 4 — Explorar datos (completa, MVP básico)

**Frontend** (`frontend/src/pages/Explorar.tsx`):
- **"¿Qué quieres descubrir hoy?"**: 4 análisis predefinidos (Tendencia de ventas, Productos
  estrella, Categorías rentables, Canales y sucursales) que configuran el análisis con un clic.
- **"Define tu análisis"**: rango (todo el periodo o mes), agrupar por (mes/categoría/
  producto/canal-sucursal) y métrica (ingresos o utilidad si el archivo trae costos).
- **Hallazgos principales** calculados en el momento y **sin costo de IA**: variación del
  último mes, mejor/peor mes, concentración del producto top, categoría más/menos rentable,
  canal dominante, proyección y advertencias del motor.
- **Gráfico principal** (barras horizontales por agrupación o línea de tendencia) +
  **"Profundiza"** (tabla con ingresos, % del total, utilidad y margen).
- **Recomendación inteligente**: `POST /ai/recommendation` entrega recomendación + plan de
  acción de 3 pasos. **Solo a pedido del usuario** (botón) — control de costo de IA.
- **"Guardar análisis"**: persistencia best-effort en la tabla `analyses`.

**Base de datos** (`supabase/migrations/0004_analyses.sql`):
- Tabla `analyses` (configuración + hallazgos + recomendación) con RLS por usuario.

## ✅ Pasada de estabilidad multiusuario (2026-07-03)

- **Seguridad**: `storage_path` valida propiedad contra el `user_id` del JWT (la descarga usa
  la service_role key que salta RLS) → 403 si la ruta no empieza con `{user_id}/`.
- **Cambio de usuario en el mismo navegador**: `DatasetContext` se resetea al hacer logout o
  cambiar de cuenta — el archivo/métricas/panel IA del usuario anterior no quedan vivos.
- Claves de recálculo con `uploadedAt` (dos archivos con igual nombre ya no se confunden).
- `VITE_API_BASE_URL` obligatoria en producción (error claro en vez de fallback a localhost).
- Log seguro de CORS (Origin + ruta, jamás tokens) para diagnosticar despliegues.
- Tests: **18 pruebas** (nuevas: storage_path ajeno → 403, preflight CORS, `/ai/*` protegidos
  y con 503 claro sin `ANTHROPIC_API_KEY`).

## ✅ Fase 5 — Alertas, Historial, Reportes, Configuración y planes (completa salvo Conectores)

**Alertas** (`frontend/src/pages/Alertas.tsx`):
- Reglas configurables con umbral y toggle (caída de ingresos m/m, margen bajo,
  concentración de producto, concentración de canal, advertencias del motor), guardadas
  en el navegador. Cada alerta: qué pasó, severidad (crítica/media/baja), área afectada
  y recomendación. Panel derecho: resumen por severidad y por área. "Marcar revisada".

**Historial** (`frontend/src/pages/Historial.tsx` + `lib/history.ts`):
- Archivos cargados (fecha, filas, calidad %, estado) y actividad completa desde Supabase.
- **Retomar**: descarga el archivo desde Storage (RLS de carpeta propia), re-estandariza y
  rehidrata el `DatasetContext` → continuar en Limpieza tras refrescar el navegador.

**Reportes** (`frontend/src/pages/Reportes.tsx` + `lib/report.ts`):
- **Reporte ejecutivo PDF**: vista imprimible con la marca (KPIs, evolución, categorías,
  canales, top productos, proyección) → "Guardar como PDF". **Excel/CSV es-CL**
  (separador `;`, BOM UTF-8) con todas las tablas. Sin dependencias nuevas.

**Configuración** (`frontend/src/pages/Configuracion.tsx` + `lib/profile.ts`):
- Perfil editable (nombre, empresa, RUT, país, teléfono → tabla `profiles`), preferencias
  de datos es-CL, plan de la cuenta y consultas IA usadas/límite del mes (`GET /ai/usage`).

**Planes y cuotas IA** (`api/app/quota.py`, SPEC §9):
- Cada consulta IA (resumen, chat, recomendación) descuenta del cupo mensual del plan
  (`profiles.plan`): básico 20, gold 200 (configurables con `AI_MONTHLY_LIMIT_*`).
- Cupo agotado → **429** con mensaje claro y CTA a Gold. Registro en `ai_usage`
  (migración `0006`). Sin Supabase (dev) el gating se desactiva limpio.

**Hardening multiusuario (backend)**:
- Descarga desde Storage con **límite de 15 MB** (Content-Length + corte en streaming).
- pandas y la descarga corren en el **threadpool**: el event loop queda libre y varios
  usuarios pueden procesar archivos a la vez (antes se bloqueaban entre ellos).
- Migración `0005`: RLS valida que `dataset_id` pertenezca al usuario en
  `cleaning_jobs`, `activity_log` y `analyses`.
- Tests: **22 pruebas** (incluye 413 de Storage, 429 de cuota y ES256/JWKS real).

## ✅ Fase 6 — Conectores + endurecimiento (completa)

**Conectores** (`frontend/src/pages/Conectores.tsx` + `api/app/routes/connectors.py`):
- **Google Sheets funcional sin OAuth**: se pega el enlace de una hoja pública o
  compartida por enlace; la API extrae el ID, arma ella la URL oficial de export CSV
  (sin SSRF), descarga con tope de 15 MB y detecta hojas privadas con instrucción clara.
  El archivo entra al mismo pipeline que un Excel subido.
- Tarjetas Excel/CSV (disponible), Base de datos SQL y otras integraciones (próximamente).
- **Hook `useFileImport` compartido** entre Estandarización y Conectores (un solo flujo).

**Endurecimiento** (tras revisión crítica externa + propia):
- `saveCleaningJob` best-effort real: un fallo de Supabase ya no se muestra como error de
  limpieza; la UI avisa suave y el error queda en consola.
- Reporte PDF con **escape de HTML** en todos los datos del usuario; CSV con
  **neutralización de formula injection** (`=`, `+`, `-`, `@`).
- Historial distingue **error de Supabase vs historial vacío**; Retomar de un dataset
  `limpio` re-aplica la limpieza y deja el Resumen operativo de inmediato.
- Reglas de alertas guardadas **por usuario** (no globales por navegador).
- `/ai/*` rechaza contextos de métricas > 200 KB (413); `record_usage` loguea respuestas
  de error de `ai_usage` (típico: migración 0006 sin ejecutar).
- Tests: **27 pruebas**.


## ✅ Fase 7 — Planes, limpieza dirigida y motor profesional (completa)

**Planes y capacidades** (`api/app/capabilities.py` + `frontend/src/lib/plans.ts`):
- Tres planes: **Básico → Analista → Gold (en construcción: SQL + comunidad)**.
  Migración `0008` renombra los `gold` legacy a `analista`. Matriz única de
  capacidades consumida por backend y frontend.
- **`PLAN_ENFORCEMENT` / `VITE_PLAN_ENFORCEMENT` en `false`**: todas las funciones
  desbloqueadas para probar; cada puerta (403 del backend, candados de la UI) ya está
  instalada — encender el flag no requiere tocar componentes.
- **Página Planes** (`/planes`, ítem nuevo del sidebar): 3 tarjetas desde la matriz,
  Gold con badge "En construcción", sección de **tokens addon** con cupo del mes,
  saldo y botón "Solicitar más" (queda en `addon_requests`; se atiende a mano).
- Básico limpia y estandariza igual que todos, pero (con enforcement) **no descarga**
  la base limpia ni los reportes.

**Limpieza dirigida por variables** (`POST /clean/assisted`):
- Chat horizontal al pie de Limpieza (Analista/Gold): el usuario escribe qué columnas
  y reglas quiere y el botón **"Limpiar con mis variables"** corre el motor dirigido.
  El botón superior **"Limpiar datos"** (reglas por defecto) sigue para todos.
- **2 intentos base/mes** (`AI_CLEANING_MONTHLY_LIMIT`) + **tokens addon** (ledger
  `plan_addons`, migración `0009`; saldo = suma; consumos = filas negativas del
  sistema, auditable). Advertencia visible de intentos; 429 con CTA a Planes al
  agotarse; instrucciones no reconocidas → 422 **sin consumir** el intento.
- Cupos separados por `kind` en `ai_usage`: la limpieza no gasta el cupo de insights.
- `POST /admin/grant-credits` (solo `profiles.is_admin`) otorga tokens a mano
  (alternativa por SQL en el README). `GET /plans/usage` alimenta Planes y Configuración.

**Costuras IA (preparadas, APAGADAS)**:
- `engine/directed.py` → `interpret_cleaning_instructions` (hoy determinista:
  columnas mencionadas + catálogo acotado de reglas; un solo `# TODO IA`).
- `engine/ai_refine.py` → `refine_with_ai` (paso final opcional del pipeline, flag
  `AI_REFINE_ENABLED=false`): la IA "termina el último 10–20%" cuando se active.

**Motor profesional** (`api/app/engine/`):
- Nulos numéricos **nunca imputados con 0** (quedan NaN para métricas, catalogados y
  marcados en la descarga); outliers IQR **solo en roles métricos**; duplicados con
  criterio explícito + advertencia sin columna ID; tipo por **muestra aleatoria
  determinista con confianza**; convención numérica **por columna** ("850.000");
  fechas con **dayfirst dominante** y meses en texto; **fuzzy matching** de typos;
  **Excel multi-hoja** + detección de fila de encabezados; **caché del pipeline**
  (cambiar el periodo no re-limpia); **reporte de calidad por columna**.
- **Mapeo de columnas editable** en Limpieza (respetado por /clean, /metrics y
  descargas en toda la app; persistencia best-effort en `dataset_columns`).

**Layout**: el panel Asistente IA vive **solo en Resumen y Explorar datos**; el resto
de pantallas usa todo el ancho.

**Tests**: **57 pruebas** de la API (24 nuevas de la Fase 7), `npm run build` verde.

## ✅ Fase 8 — Administración, soporte, gating comercial y adaptividad (completa)

**Administración** (`/admin` + `api/app/routes/admin.py`, migración `0010`):
- Cuenta administradora `servicios@adsveris.com` (`profiles.is_admin`): acceso a TODO
  sin depender de planes (capacidades y cupos ilimitados).
- Página **Administrar cuentas**: todas las cuentas con semáforo (🔴 solicitudes
  pendientes / 🟢 al día), detalle con datos visibles (nunca contraseñas), **activación
  manual de planes** y otorgamiento de tokens. Bandeja unificada de soporte + addons
  con "marcar atendida". Todo cambio manual queda auditado en `admin_audit`.
- **Costura de pasarela de pago**: `set_user_plan()` (backend) y `startCheckout()`
  (frontend) son los únicos puntos a tocar cuando exista el checkout.

**Soporte** (`api/app/routes/support.py`): el botón "¿Necesitas ayuda?" abre un modal
que registra la solicitud (`support_requests`); responde una persona del equipo.

**Gating comercial encendido** (`PLAN_ENFORCEMENT=true` por defecto):
- Base limpia (Excel/CSV) y limpieza dirigida → Plan Analista+; el reporte PDF del
  negocio es para TODOS los planes. Función bloqueada → aviso `PlanUpsell` con
  "Ir a comprar el plan". Sin Supabase (dev) → fail-open.
- Cupo de limpieza dirigida por plan: **10/mes Analista, 25/mes Gold** + tokens addon.

**Retención de Storage** (`POST /storage/retention`, tras cada subida): tope por plan
(10/25/50 archivos), purga de no usados > 60 días, los 5 más recientes intocables;
datasets purgados quedan en el historial con `storage_path` null.

**Adaptividad**: `/metrics` expone `dimensiones`; Explorar oculta análisis imposibles
(sin canal → sin recuadro de canales) y Resumen muestra KPIs reales de ingresos cuando
no hay costos (nada de tarjetas en "—"), con tarjetas de canal/categoría/productos solo
si existen esas columnas.

**Motor §5.14**: monedas ("$", "CLP", "US$", "€"), porcentajes, negativos contables
"(1.500)" y filas de totales al final excluidas con aviso.

**UI**: Limpieza rediseñada (pasos horizontales, mapeo a lo ancho, sin espacio muerto),
botón "Descargar base actualizada" con tarjeta y botón primario propios, tonos suaves
en Resumen/Limpieza/Estandarización/Admin.

**Tests**: **80 pruebas** de la API (18 nuevas de Fase 8), build verde y 2 E2E
Playwright (pipeline completo + adaptividad con archivo mínimo).


## ✅ Fase 9 — Mapeo universal: diccionario de roles y biblioteca de prompts (completa)

**El problema**: el mapeo automático usaba ~40 palabras clave fijas para 10
roles. Insuficiente para limpiar "cualquier" base de datos PyME.

**La solución** (dos activos de datos + tres módulos):
- `api/app/data/palabras_clave_roles.csv` — **≈15.600 claves únicas, 64 roles,
  12 grupos** (es-CL + inglés, abreviaturas, RUT/DTE/UF/AFP, plurales y
  compuestos reales). La columna `rol_motor_actual` marca la equivalencia
  segura con los 10 roles del motor: el CSV mejora el mapeo HOY y deja listos
  54 roles extendidos (rut, email, saldo, precio_unitario, stock, ...) para
  cuando el motor de métricas los consuma.
- `engine/dictionary.py` — matching en 4 etapas (exacto → contención por
  tokens → prefijo → fuzzy Levenshtein), empates por largo y prioridad, carga
  única + memoización.
- `mapping.py` en dos pasadas — diccionario primero, **palabras clave legacy
  como red de compatibilidad** para roles vacíos: cero regresiones (los 80
  tests previos pasan intactos) y más precisión cuando existe una columna
  mejor ("Total Neto" gana monto; "Precio Unitario" ya no se suma como ingreso).
- `api/app/data/prompts_estandarizacion_por_rol.txt` + `engine/prompt_library.py`
  — biblioteca de prompts por grupo de roles con catálogo acotado (la IA
  decide/corrige residuos y devuelve JSON validable; el motor transforma).
  Incluye el clasificador de columnas sin match ([PROMPT B]) y el prompt de
  refinado global ([PROMPT C], interfaz exacta de `refine_with_ai`).
- `engine/ai_classifier.py` — costura del clasificador IA, **preparada y
  APAGADA** (`AI_CLASSIFIER_ENABLED=false`): el fallback que convierte el
  diccionario finito en cobertura universal cuando se encienda.

**API**: `/standardize` expone `mapeo_extendido` (rol, método, confianza por
columna); el `reporte_calidad` de `/clean` suma `rol_extendido`, `grupo_rol` y
`match_diccionario`.

**Tests**: 97 en verde (17 nuevos de la Fase 9).

## ✅ Fase 10 — Endurecimiento comercial (completa)

Ver el detalle en `CHANGELOG.md` [0.11.0]. Resumen: migración **0011** (P0:
plan/is_admin ya no editables por `authenticated`), cobertura de costos y
nombres financieros honestos, moneda detectada, comparación mensual calendario,
fix del contexto de periodo, fuzzy sin identificadores, duplicados seguros sin
ID, scope estricto, export con hoja Observaciones, guardias de carga (.xls
fuera, anti ZIP-bomb), selector de hoja end-to-end, 60 entradas del diccionario
reclasificadas + test de auditoría, responsive completo (hamburguesa + drawer
IA sin consumo oculto), recuperar contraseña, anti-spam de soporte, créditos
auditados, deps fijadas y CI. **118 tests + build + 2 E2E.**

## ✅ Fase 11 — Rendimiento con datos grandes, precisión del motor y continuidad (completa)

Ver el detalle en `CHANGELOG.md` [0.12.0]. Resumen: caché del pipeline por
**presupuesto de celdas** (2,4 M totales, LRU — los archivos grandes también se
cachean y los módulos dejan de reprocesar), parseo por **valores únicos**
(50.000×8: ~13,3 s → ~1,8 s), loader vectorizado, "Retomar" sin descargar el
archivo al navegador; números US (`1,234.56`), fechas mixtas con evidencia por
valor + aviso, pagada→pagado con guardas conservadoras, `resolve_mapping` que
fusiona el mapeo del usuario con el automático; timeouts con "Reintentar",
claves de recálculo con mapeo/hoja, moneda activa real, CTA cuando no hay
columna de monto; restauración del último trabajo al iniciar sesión,
"Estandarizar nuevo documento", retención también al login y contactos de ayuda
(WhatsApp/Instagram/correo). **129 tests + build + 3 E2E.**

## ✅ Fase 12 — Bloques 1 a 6

- Detección siempre activa y eliminación por defecto en `false`, aunque exista
  una columna cuyo nombre parezca identificador.
- Clasificación separada de exactos originales, normalizados adicionales,
  conflictos de ID y posible granularidad omitida.
- Acción prominente "Eliminar duplicados exactos" con confirmación; el texto libre
  de la limpieza dirigida no puede conceder ese permiso.
- Decisión coherente en limpieza, métricas, descarga, IA, caché e historial.
- Fila física y hoja de origen conservadas como metadatos, sin añadir columnas al
  dataset del usuario; exportadas en `Observaciones`.
- Migración `0012_cleaning_job_options.sql` para persistir la decisión explícita.
  Script de regresión real versionado, archivo REQ5325 fuera del repositorio.
- Conteos por categoría con unidades honestas; una celda textual se contabiliza
  una sola vez aunque pase por varias normalizaciones.
- Montos cero, negativos y atípicos IQR separados y solo señalizados, con
  parámetros estadísticos por columna.
- Placeholders de cliente preservados como nulos semánticos; vacíos físicos y
  patrones estructurales informados por separado, sin imputación.
- Mojibake reparado solo si latin-1/cp1252 strict mejora inequívocamente el texto;
  original, propuesta, método y confianza quedan auditados.
- Incoherencias nombre↔ID detectadas en ambos sentidos, con ejemplos y filas de
  origen; son observaciones y nunca autorizan cambios automáticos.
- Fórmulas `.xlsx` auditadas solo en filas reales de datos, separando fórmulas
  volátiles y fórmulas en identificadores.
- Pestañas por hoja con estado propio; descarga XLSX gobernada por un manifiesto
  explícito que registra también las hojas no procesadas.
- Combinación opcional solo para estructuras idénticas, con `hoja_origen` y
  confirmación. Los JOIN entre estructuras distintas quedan pendientes porque
  requieren que el usuario declare una clave común y la cardinalidad esperada.
- Bloque 6A completo: eliminación confirmada desde Historial mediante una saga
  reintentable Storage→PostgreSQL; la fase de base es una RPC transaccional y el
  trabajo sobrevive al dataset mediante la migración `0013`.
- Bloque 6B completo: mapeo colapsado por defecto, chips de asignaciones, panel
  de roles relevantes, confianza semántica y CTA directo desde Resumen. La
  desasignación se conserva como override explícito.

## ⏳ Pendiente (operación comercial)

- **Pasarela de pago** (Webpay/Flow/MercadoPago): reemplazar `startCheckout()` y
  llamar `set_user_plan(source="pasarela")` desde el webhook. La activación manual
  del admin queda como respaldo.
- Encender el clasificador IA de columnas (`AI_CLASSIFIER_ENABLED`) y conectar
  los prompts de grupo a los residuos por columna (`ejemplos_invalidos` del
  reporte de calidad) — la biblioteca de prompts ya está en el repo.
- Consumir los roles extendidos del diccionario (rut, email, saldo,
  precio_unitario, stock, ...) en métricas y validaciones específicas por rol.
- Activar las costuras IA del motor: `interpret_cleaning_instructions` (interpretación
  libre por IA) y `refine_with_ai` (`AI_REFINE_ENABLED`) — un prompt cada una.
- Notificación por correo al admin cuando llega una solicitud de soporte (hoy: semáforo
  en Administrar cuentas).
- Vigilancia continua de Alertas (evaluación programada + correo/notificaciones).
- Conector SQL / integraciones POS-facturación (Bsale, Defontana, Jumpseller, Shopify).
- Reportes generados en backend (.xlsx real y PDF descargable).
- Cuota IA con control atómico en BD (hoy check-then-record: una ráfaga simultánea
  justo en el límite puede excederlo por unas pocas consultas). Aplica también al
  cupo de limpieza dirigida.
- Cuotas atómicas por RPC SQL y persistencia transaccional del pipeline
  (estandarización/limpieza/mapeo hoy son pasos best-effort encadenados).
- Paginación y agregaciones SQL del panel Administrar cuentas (hoy tope de
  200 cuentas leídas por request).
- Correo transaccional de soporte y de cambio de plan (hoy: bandeja +
  "Mis solicitudes" en el modal de ayuda).
- Benchmark del diccionario con precision/recall por rol sobre un corpus real
  de encabezados PyME etiquetado a mano.
- Términos y condiciones, política de privacidad formal, eliminación de cuenta
  y MFA (requisitos legales del lanzamiento amplio).
- Deuda técnica: transporte por `dataset_id` (hoy `storage_path` validado por prefijo);
  purga de Storage programada en el servidor (hoy: opportunista al subir).

## Comandos para correr el proyecto

```bash
# ── Frontend ──────────────────────────────────────────────
cd frontend
cp .env.example .env          # completa VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_BASE_URL
npm install
npm run dev                   # http://localhost:5173
npm run build                 # build de producción (dist/)

# ── API Python ────────────────────────────────────────────
cd api
cp .env.example .env          # completa las variables secretas del backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000    # http://localhost:8000/health

# Tests de la API
pip install -r requirements-dev.txt
python -m pytest tests/ -v

# ── Supabase ──────────────────────────────────────────────
# SQL Editor → ejecutar en orden:
#   supabase/migrations/0001_profiles.sql
#   supabase/migrations/0002_datasets_pipeline.sql
#   supabase/migrations/0003_profile_contact_fields.sql
#   supabase/migrations/0004_analyses.sql
#   supabase/migrations/0005_rls_dataset_ownership.sql
#   supabase/migrations/0006_ai_usage.sql
#   supabase/migrations/0007_public_table_grants.sql
#   supabase/migrations/0008_plans.sql          (Fase 7: 3 planes + is_admin)
#   supabase/migrations/0009_cleaning_credits.sql (Fase 7: tokens y solicitudes)
#   supabase/migrations/0010_admin_support.sql  (Fase 8: admin, soporte y auditoría)
#   supabase/migrations/0011_lock_privileged_columns.sql (Fase 10: P0 — plan/is_admin solo backend)
#   supabase/migrations/0012_cleaning_job_options.sql (Fase 12 B1: decisión explícita de duplicados)
#   supabase/migrations/0013_dataset_deletion_saga.sql (Fase 12 B6A: eliminación recuperable)
#   supabase/migrations/0014_restore_snapshots.sql
#   supabase/migrations/0015_sin_plan_nuevas_cuentas.sql (Fase 13: cuentas nuevas sin plan) (restauración persistente y segura)
```

**Modo desarrollo sin Supabase**: levanta la API con `DEV_AUTH_BYPASS=true` (y sin
`SUPABASE_JWT_SECRET`) para probar el pipeline local sin autenticación. Jamás en producción.

**Datos de ejemplo**: `api/tests/data/ventas_ejemplo.csv` (ventas con errores intencionales:
duplicados, nulos, fechas inválidas, textos inconsistentes, columna vacía y un outlier).
