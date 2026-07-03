# Estado del proyecto por fases — ADS Veris

**Estado actual: Fases 0, 1 y 2 completas.** Próxima: Fase 3 (Asistente IA).

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

## ⏳ Pendiente — Fase 3 y posteriores

- **Fase 3 — Asistente IA**: resumen automático + chat anclado a los datos (Anthropic API desde el backend, `ANTHROPIC_MODEL` configurable) + gating por plan.
- **Fase 4 — Explorar datos**: análisis guiados, hallazgos, recomendación inteligente.
- **Fase 5**: Alertas, Historial (UI), Conectores (Google Sheets/SQL), Reportes PDF/Excel, Configuración avanzada y planes.

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
```

**Modo desarrollo sin Supabase**: levanta la API con `DEV_AUTH_BYPASS=true` (y sin
`SUPABASE_JWT_SECRET`) para probar el pipeline local sin autenticación. Jamás en producción.

**Datos de ejemplo**: `api/tests/data/ventas_ejemplo.csv` (ventas con errores intencionales:
duplicados, nulos, fechas inválidas, textos inconsistentes, columna vacía y un outlier).
