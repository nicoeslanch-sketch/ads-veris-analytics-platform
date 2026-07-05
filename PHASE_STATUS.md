# Estado del proyecto por fases — ADS Veris

**Estado actual: Fases 0 a 6 completas — todo el roadmap del SPEC está construido.**
La Fase 6 cierra Conectores (Google Sheets funcional) y endurece reportes y persistencia.
La microfase 6.1 suma estabilidad: persistencia visible, origen Google Sheets, retomar con
reglas reales de limpieza y controles de entrada del conector.
Lo que resta es una fase opcional de operación comercial (ver "Pendiente").

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

## ⏳ Pendiente (fase opcional de operación comercial)

- Checkout/upgrade real de plan Gold (hoy el plan se cambia en la tabla `profiles`).
- Vigilancia continua de Alertas (evaluación programada + correo/notificaciones).
- Conector SQL / integraciones POS-facturación (Bsale, Defontana, Jumpseller, Shopify).
- Reportes generados en backend (.xlsx real y PDF descargable).
- Cuota IA con control atómico en BD (hoy check-then-record: una ráfaga simultánea
  justo en el límite puede excederlo por unas pocas consultas).
- Deuda técnica: transporte por `dataset_id` (hoy `storage_path` validado por prefijo).

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
```

**Modo desarrollo sin Supabase**: levanta la API con `DEV_AUTH_BYPASS=true` (y sin
`SUPABASE_JWT_SECRET`) para probar el pipeline local sin autenticación. Jamás en producción.

**Datos de ejemplo**: `api/tests/data/ventas_ejemplo.csv` (ventas con errores intencionales:
duplicados, nulos, fechas inválidas, textos inconsistentes, columna vacía y un outlier).
