# ADS Veris — Plataforma de Análisis de Datos

Plataforma de análisis de datos para PyMEs chilenas: el corazón de ADS Veris.
Limpieza automática y personalizada de datos, dashboard con KPIs y ratios financieros,
y un asistente con IA que interpreta los datos del negocio.
**La solución asequible para PyMEs que no pueden pagar un analista de datos.**

> Especificación completa: [`SPEC.md`](./SPEC.md) · Estado por fases y comandos:
> [`PHASE_STATUS.md`](./PHASE_STATUS.md) · Cambios: [`CHANGELOG.md`](./CHANGELOG.md)

## Arquitectura

```
frontend/   React + Vite + TypeScript + Tailwind v4  →  deploy en Vercel
api/        FastAPI + pandas (motor de datos + IA)   →  deploy en Render/Railway
supabase/   Migraciones SQL (Postgres + Auth + Storage + RLS)
```

- El **frontend** habla con Supabase (auth, datos, storage) y con la **API Python** (estandarización, limpieza, métricas, IA).
- Las llamadas a **Anthropic (Claude)** se hacen **solo desde la API Python** — la key jamás llega al navegador.
- Todos los endpoints sensibles de la API validan el **JWT de Supabase** del usuario.
- Los archivos se suben directo del navegador a **Supabase Storage**; la API los lee vía signed URL.

## Requisitos

- Node 18+ (probado con Node 22)
- Python 3.11+
- Una cuenta de [Supabase](https://supabase.com) (plan gratuito sirve)

## Setup

### 1. Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com).
2. Ve a **SQL Editor** y ejecuta en orden:
   - `supabase/migrations/0001_profiles.sql` (perfiles con RLS + trigger de registro)
   - `supabase/migrations/0002_datasets_pipeline.sql` (datasets, limpieza, historial y
     bucket privado `datasets` en Storage)
   - `supabase/migrations/0003_profile_contact_fields.sql` (pais y telefono en registro)
   - `supabase/migrations/0004_analyses.sql` (análisis guardados de Explorar datos)
   - `supabase/migrations/0005_rls_dataset_ownership.sql` (RLS estricta sobre dataset_id)
   - `supabase/migrations/0006_ai_usage.sql` (consumo IA para cuotas por plan)
   - `supabase/migrations/0007_public_table_grants.sql` (permisos PostgREST para tablas con RLS)
   - `supabase/migrations/0008_plans.sql` (Fase 7: planes basico|analista|gold,
     `is_admin`, rol `costo` y mapeo editable)
   - `supabase/migrations/0009_cleaning_credits.sql` (Fase 7: `kind = cleaning`,
     ledger `plan_addons` y `addon_requests`)
   - `supabase/migrations/0010_admin_support.sql` (Fase 8: cuenta administradora
     `servicios@adsveris.com`, `support_requests` del botón de ayuda y auditoría
     `admin_audit`. Si esa cuenta se crea DESPUÉS de correr la migración, repite el
     UPDATE del paso 1 del archivo)
   - `supabase/migrations/0011_lock_privileged_columns.sql` (**Fase 10 — SEGURIDAD
     P0, obligatoria antes de aceptar usuarios externos**: bloquea que un usuario
     edite su propio `plan` / `is_admin` por la REST API; el navegador solo puede
     actualizar sus datos de contacto)
   - `supabase/migrations/0012_cleaning_job_options.sql` (**Fase 12, Bloque 1**:
     persiste en cada limpieza la decisión explícita y segura de eliminar o no
     duplicados exactos)
   - `supabase/migrations/0013_dataset_deletion_saga.sql` (**Fase 12, Bloque 6A**:
     eliminación recuperable de Storage + PostgreSQL, trabajos reintentables y
     finalización transaccional con historial retenido)
   - `supabase/migrations/0014_restore_snapshots.sql` (snapshot versionado y
     privado para restaurar el último trabajo sin reprocesar el archivo)
3. Copia de **Settings → API**: la `URL`, la `anon key`, la `service_role key` y el `JWT Secret`.

### 2. Frontend

```bash
cd frontend
cp .env.example .env    # completa VITE_SUPABASE_URL y VITE_SUPABASE_ANON_KEY
npm install
npm run dev             # http://localhost:5173
```

### 3. API Python (motor de datos)

```bash
cd api
cp .env.example .env    # completa las variables secretas (ver tabla abajo)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health
```

Tests del pipeline (usa `api/tests/data/ventas_ejemplo.csv` como datos de ejemplo):

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

> **Desarrollo sin Supabase**: `DEV_AUTH_BYPASS=true uvicorn app.main:app --reload`
> permite probar el pipeline sin autenticación. Solo para local; jamás en producción.

## Variables de entorno

**Frontend (públicas, prefijo `VITE_` — van al bundle):**

| Variable | Descripción |
|---|---|
| `VITE_SUPABASE_URL` | URL del proyecto Supabase |
| `VITE_SUPABASE_ANON_KEY` | Clave anónima (protegida por RLS) |
| `VITE_API_BASE_URL` | URL del motor de datos FastAPI |

**Backend (secretas — jamás en React/Vite):**

| Variable | Descripción |
|---|---|
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave service_role (solo backend) |
| `SUPABASE_JWT_SECRET` | Secreto para validar los JWT de los usuarios |
| `SUPABASE_STORAGE_BUCKET` | Bucket de Storage para archivos (default: `datasets`) |
| `ANTHROPIC_API_KEY` | API key de Anthropic (Claude) — se usa desde la Fase 3 |
| `ANTHROPIC_MODEL` | Modelo configurable (ej: `claude-haiku-4-5-20251001`) |
| `AI_MONTHLY_LIMIT_BASICO` | Cupo mensual de consultas IA del plan básico (default: 20) |
| `AI_MONTHLY_LIMIT_GOLD` | Cupo mensual de consultas IA del plan Gold (default: 200) |
| `ALLOWED_ORIGINS` | Orígenes CORS permitidos, separados por coma |
| `DEV_AUTH_BYPASS` | Solo desarrollo local sin Supabase (default: `false`) |
| `STRUCTURAL_NULL_GROUP_EMPTY_THRESHOLD` | Proporción vacía dentro del grupo para señalar un posible nulo estructural (default: `0.98`) |
| `STRUCTURAL_NULL_OUTSIDE_FILLED_THRESHOLD` | Proporción informada fuera del grupo (default: `0.95`) |
| `STRUCTURAL_NULL_MIN_GROUP_SIZE` | Tamaño mínimo del grupo estructural (default: `20`) |
| `STRUCTURAL_NULL_MAX_GROUP_CARDINALITY` | Máximo de categorías de la variable agrupadora (default: `50`) |

## Deploy

### Frontend en Vercel (proyecto Vite, no Next.js)

```
Framework / Preset: Vite
Root Directory:     frontend
Build Command:      npm run build
Output Directory:   dist
Install Command:    npm install
```

Si Vercel muestra `Other`, complétalo manualmente con esos valores. Configura las
variables `VITE_*` en el proyecto de Vercel. El rewrite SPA ya está en `frontend/vercel.json`.

### API Python en Render/Railway

- Comando de inicio: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Directorio raíz: `api/`
- Versión de Python fijada en `api/.python-version` (3.11.9) para builds reproducibles.
- Configura ahí las variables secretas del backend.
- Health check: `GET /health`.

## Estado del proyecto (roadmap por fases)

- [x] **Fase 0 — Scaffold + marca + shell**: tokens de marca, Poppins, layout (sidebar,
  topbar, panel IA), routing, auth Supabase, migración `profiles`, esqueleto FastAPI con JWT.
- [x] **Fase 1 — Pipeline de datos**: `/standardize`, `/clean`, `/metrics` con pandas;
  módulos de Estandarización y Limpieza funcionales; migración de datasets/limpieza/historial;
  lectura desde Supabase Storage; tests con datos de ejemplo.
- [x] **Fase 2 — Resumen (dashboard)**: KPIs con variación y sparklines, evolución de
  ingresos/gastos/utilidad, análisis por categoría, ventas por canal, top productos,
  proyección a 3 meses y filtro de periodo funcional en el topbar.
- [x] **Fase 3 — Asistente IA**: resumen automático + preguntas sugeridas + chat con
  streaming anclado a los datos (Anthropic API solo en el backend, JWKS para tokens
  ES256 de Supabase). Gating por plan queda para la Fase 5.
- [x] **Fase 4 — Explorar datos**: análisis predefinidos y personalizados (rango, agrupar
  por, métrica), hallazgos automáticos, tabla "Profundiza", recomendación inteligente con
  plan de acción (a pedido) y guardar análisis (migración `0004`).
- [x] **Fase 5 — Alertas, Historial, Reportes, Configuración y planes**: alertas con
  reglas configurables (severidad, área, recomendación), Historial con "Retomar" desde
  Storage, reportes PDF/Excel, Configuración con perfil editable y contador de consultas
  IA, cuotas mensuales por plan (Básico/Analista; `gold` interno) con 429 al agotarse.
- [x] **Fase 6 — Conectores + endurecimiento**: importación desde **Google Sheets**
  (hoja pública/compartida por enlace, sin OAuth) al mismo pipeline; escape de HTML y
  anti formula-injection en reportes; persistencia best-effort con avisos visibles.
- [x] **Microfase 6.2 — preparación comercial**: capabilities por plan, descarga de base
  limpia solo para Plan Analista y export seguro contra formula injection.
  Pendiente (operación comercial): checkout Analista, conector SQL, alertas continuas y
  reportes generados en backend.
- [x] **Fase 12, Bloques 1–6 — motor no destructivo, multihoja y UX segura**: detección automática,
  eliminación desactivada por defecto y disponible solo mediante confirmación explícita;
  exactos originales separados de coincidencias normalizadas, diagnóstico de IDs,
  fila física de origen y decisión persistida; categorías con unidades separadas,
  contador textual sin duplicación, controles independientes de cero/negativos/IQR,
  placeholders por rol, nulos estructurales, reparación strict de mojibake,
  incoherencias nombre↔ID, auditoría conservadora de fórmulas Excel y descarga
  multihoja gobernada por un manifiesto explícito (combinación solo con
  encabezados idénticos y confirmación); eliminación recuperable desde Historial
  y mapeo progresivo basado en confianza semántica. El pipeline comparte etapas
  con cachés LRU acotados, optimiza Excel sin fórmulas y carga el frontend por
  rutas para reducir tanto el procesamiento repetido como el bundle inicial.

## Regla de flujo no negociable

Si el usuario no ha cargado y limpiado datos, la plataforma no muestra dashboard.
**Todo parte de los datos.**

## Planes, tokens y administración (Fase 7)

- **Interruptor de planes**: el gating vive tras `PLAN_ENFORCEMENT` (backend) y
  `VITE_PLAN_ENFORCEMENT` (frontend). En Fase 7 ambos van en `false`: todo queda
  accesible para probar y las puertas ya están instaladas. Para activar el modelo
  comercial basta poner ambos en `true` y redeployar — sin tocar código.
- **Limpieza dirigida**: 2 intentos base al mes (`AI_CLEANING_MONTHLY_LIMIT`).
  Los intentos extra se venden como **tokens addon**: el usuario los pide desde la
  página Planes (botón "Solicitar más" → tabla `addon_requests`) y ADS Veris los
  otorga a mano.
- **Otorgar tokens** (dos caminos equivalentes):
  1. **Endpoint admin** (recomendado): marca tu usuario como admin una vez
     (`update public.profiles set is_admin = true where id = '<TU-UUID>';`) y llama
     `POST /admin/grant-credits` con `{"user_id": "<uuid-del-cliente>", "credits": 5,
     "note": "Compra 5 tokens"}` (con tu JWT).
  2. **SQL directo en Supabase**:
     ```sql
     insert into public.plan_addons (user_id, credits, granted_by, note)
     values ('<uuid-del-cliente>', 5, 'manual', 'Compra 5 tokens');
     ```
  El saldo del usuario es `sum(credits)` de su ledger; los consumos quedan como filas
  negativas insertadas por el sistema (auditable).
- **Solicitudes pendientes**: `select * from public.addon_requests where status = 'pendiente';`
  y márcalas atendidas con `update ... set status = 'atendida'`.
- **Costuras IA del motor** (apagadas): `AI_REFINE_ENABLED=false` controla el refinado
  final (`api/app/engine/ai_refine.py`); la interpretación de instrucciones vive en
  `api/app/engine/directed.py`. Cada una tiene un único `# TODO IA` con interfaz
  estable: activarlas es reemplazar el cuerpo por la llamada a Anthropic.

## Mapeo universal de columnas (Fase 9)

- El rol de cada columna se detecta contra el **diccionario**
  `api/app/data/palabras_clave_roles.csv` (≈15.600 claves, 64 roles, 12 grupos)
  en 4 etapas: exacto → contención por tokens → prefijo → fuzzy. Los roles del
  motor (10) se llenan primero desde el diccionario y las palabras clave legacy
  actúan como red de compatibilidad.
- **Agregar cobertura** (un rubro nuevo, sinónimos de un cliente): edita el CSV
  (separador `;`, columnas palabra_clave/rol/grupo/tipo_dato/idioma/prioridad/
  rol_motor_actual) y despliega — sin tocar código. `rol_motor_actual` solo se
  completa cuando la equivalencia con los 10 roles del motor es segura (un
  precio unitario NO es un monto: sumarlo duplicaría ingresos).
- La **biblioteca de prompts** (`api/app/data/prompts_estandarizacion_por_rol.txt`)
  alimenta las costuras IA: clasificador de columnas sin match
  (`AI_CLASSIFIER_ENABLED`, apagado), prompts de grupo por rol y el refinado
  global (`AI_REFINE_ENABLED`, apagado). La IA decide y corrige residuos con
  JSON validable; el motor determinista transforma.
