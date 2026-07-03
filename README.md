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
| `ANTHROPIC_MODEL` | Modelo configurable (ej: `claude-opus-4-8`) |
| `ALLOWED_ORIGINS` | Orígenes CORS permitidos, separados por coma |
| `DEV_AUTH_BYPASS` | Solo desarrollo local sin Supabase (default: `false`) |

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
- [ ] **Fase 5 — Alertas, Historial, Conectores, Reportes, Configuración avanzada y planes.**

## Regla de flujo no negociable

Si el usuario no ha cargado y limpiado datos, la plataforma no muestra dashboard.
**Todo parte de los datos.**
