# Changelog — ADS Veris Plataforma de Análisis de Datos

Formato: [Keep a Changelog](https://keepachangelog.com/es/). Fases según [`SPEC.md`](./SPEC.md).

## [0.2.0] — 2026-07-02 — Fase 1: Pipeline de datos

### Agregado
- **Motor de datos** (`api/app/engine/`): carga de Excel/CSV (detección de encoding y separador),
  estandarización de textos/fechas/números con reglas es-CL, limpieza por reglas activables
  (duplicados, nulos, fechas inválidas, textos inconsistentes, tipos, columnas vacías, outliers IQR),
  métricas básicas (ingresos, evolución mensual, por categoría/canal/sucursal, top productos)
  y mapeo automático de columnas al esquema del negocio.
- **Endpoints protegidos con JWT**: `POST /standardize`, `POST /clean` (detectar/aplicar),
  `POST /metrics`. Entrada por multipart (≤15 MB) o `storage_path` de **Supabase Storage**
  (descarga con service_role key).
- **Migración `0002_datasets_pipeline.sql`**: tablas `datasets`, `dataset_columns`,
  `cleaning_jobs`, `activity_log` con RLS por usuario + bucket privado `datasets` con
  políticas por carpeta de usuario.
- **Frontend conectado a la API**: cliente con JWT (`src/lib/api.ts`), `DatasetContext`
  compartido entre módulos, persistencia best-effort en Supabase (`src/lib/datasets.ts`).
- **Página Estandarización funcional**: carga drag & drop, proceso en 3 pasos, archivos
  recientes con estado y CTA a Limpieza.
- **Página Limpieza de datos funcional**: tarjetas de estado con anillo de calidad %,
  pasos, vista previa con celdas problemáticas resaltadas, problemas detectados,
  correcciones planificadas, reglas con toggles y "Aplicar limpieza y continuar".
- Tests de la API (pytest, 10 pruebas) + datos de ejemplo `ventas_ejemplo.csv`.
- `PHASE_STATUS.md` con el estado por fases y comandos.
- Modo `DEV_AUTH_BYPASS` (solo desarrollo local sin Supabase, documentado).
- "Fuentes conectadas" del sidebar muestra el archivo cargado y su estado.

### Cambiado
- `api/requirements.txt`: + pandas, openpyxl, python-multipart. Nuevo `requirements-dev.txt` (pytest).
- `api/.env.example`: + `SUPABASE_STORAGE_BUCKET`, `DEV_AUTH_BYPASS`.
- README: instrucciones de Fase 1 (migración 0002, tests, datos de ejemplo).

## [0.1.0] — 2026-07-02 — Fase 0: Scaffold + marca + shell

### Agregado
- Frontend Vite + React + TypeScript + Tailwind v4 con tokens exactos de marca ADS Veris
  (navy, navy-deep, teal, gold, green, coral) y Poppins autoalojada.
- Shell de la app: sidebar con 9 secciones, topbar (rango de fechas es-CL, notificaciones,
  perfil con logout), panel Asistente IA inactivo.
- Autenticación Supabase (login/registro) con rutas protegidas.
- 9 páginas con estados vacíos ("sin datos, no hay dashboard").
- Migración `0001_profiles.sql`: tabla `profiles` con RLS y trigger de registro.
- API FastAPI base: `/health` público + validación JWT de Supabase (`/me` de prueba).
- `SPEC.md` (especificación de referencia), README con setup y deploy (Vercel preset Vite +
  Render/Railway), `.env.example` separados frontend/backend.
