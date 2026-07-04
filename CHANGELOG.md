# Changelog — ADS Veris Plataforma de Análisis de Datos

Formato: [Keep a Changelog](https://keepachangelog.com/es/). Fases según [`SPEC.md`](./SPEC.md).

## [0.6.0] — 2026-07-03 — Fase 5: Alertas, Historial, Reportes, Configuración y planes

### Agregado
- **Alertas (MVP)**: reglas configurables (caída de ingresos m/m, margen bajo,
  concentración de producto y de canal, advertencias del motor) evaluadas sobre el dataset
  de la sesión; cada alerta trae severidad, área y recomendación; resumen por severidad y
  por área; "Marcar revisada"; reglas persistidas en el navegador.
- **Historial funcional**: archivos cargados (estado, calidad, filas) + actividad completa
  desde Supabase, y **"Retomar"**: descarga el archivo desde Storage, re-estandariza y
  rehidrata la sesión (resuelve "si refresco pierdo el flujo").
- **Reportes (MVP)**: reporte ejecutivo en **PDF** (vista imprimible con marca) y export
  **Excel/CSV es-CL** (separador `;` + BOM) con todas las tablas del dashboard. Sin
  dependencias nuevas.
- **Configuración**: edición de perfil y empresa (tabla `profiles`), preferencias de datos
  es-CL, plan de la cuenta y **contador de consultas IA del mes** con barra de uso.
- **Cuotas y gating de IA por plan (SPEC §9)**: `ai_usage` (migración `0006`) registra cada
  consulta; `/ai/summary`, `/ai/chat` y `/ai/recommendation` validan el cupo mensual del
  plan (`AI_MONTHLY_LIMIT_BASICO=20`, `AI_MONTHLY_LIMIT_GOLD=200`, configurables) y
  responden **429 con mensaje claro** al agotarse; nuevo `GET /ai/usage`.
- Tests de la API: **22 pruebas** (límite de Storage 413, cuota 429, JWKS ES256 real
  firmado/rechazado, /ai/usage).

### Seguridad
- **Migración `0005`**: las políticas RLS de `cleaning_jobs`, `activity_log` y `analyses`
  ahora validan que el `dataset_id` referenciado pertenezca al usuario (antes solo
  validaban `user_id`).

### Corregido
- **Descarga desde Storage con límite de 15 MB** (Content-Length + corte en streaming):
  el límite del multipart ahora aplica también al flujo `storage_path` — protege la
  memoria de Render.
- **El trabajo pesado (pandas + descarga) salió del event loop** (`run_in_threadpool`):
  antes, una descarga síncrona dentro de endpoints async bloqueaba el servidor con
  usuarios concurrentes — causa probable de "con más de un usuario no deja cargar".
- Fallos de persistencia ya no son invisibles: se registran en consola y Estandarización
  muestra un aviso suave ("se procesará igual, pero no se pudo guardar en el historial").
- El auto-mes por defecto del Resumen se vuelve a aplicar al cargar un dataset nuevo.

### Cambiado
- `api/.python-version` fija Python 3.11.9 para Render.
- `.env.example` recomienda `claude-haiku-4-5-20251001` (Opus queda como alternativa
  comentada) y documenta las variables de cuota.

## [0.5.0] — 2026-07-03 — Fase 4: Explorar datos + estabilidad multiusuario

### Agregado
- **Página Explorar datos completa** (Fase 4): "¿Qué quieres descubrir hoy?" con 4 análisis
  predefinidos, "Define tu análisis" (rango, agrupar por categoría/producto/canal/mes,
  métrica ingresos/utilidad), gráfico principal (barras horizontales o tendencia),
  **Hallazgos principales** calculados automáticamente sin costo de IA (variación del último
  mes, mejor/peor mes, concentración de producto, márgenes por categoría, canal dominante,
  proyección), tabla **Profundiza** y **Recomendación inteligente** con plan de acción.
- **`POST /ai/recommendation`**: recomendación + plan de 3 pasos anclados al análisis activo.
  Se genera **solo a pedido del usuario** (botón) — control de costo de IA.
- **Migración `0004_analyses.sql`**: tabla `analyses` (análisis guardados) con RLS por usuario;
  botón "Guardar análisis" con persistencia best-effort.
- Tests de la API: 18 pruebas (7 nuevas de seguridad, CORS e IA).

### Seguridad
- **`storage_path` ahora valida propiedad**: la API descarga de Storage con la service_role
  key (salta RLS), por lo que `/standardize`, `/clean` y `/metrics` exigen que la ruta
  empiece con la carpeta del usuario autenticado (`{user_id}/...`); si no, responde **403**.

### Corregido
- **`DatasetContext` se resetea al cerrar sesión o cambiar de usuario** en el mismo
  navegador: el archivo, métricas y panel IA del usuario anterior ya no quedan vivos
  (causa probable del problema reportado con más de un usuario).
- Claves de recálculo de métricas y del panel IA ahora incluyen `uploadedAt`: subir otro
  archivo con el mismo nombre vuelve a calcular métricas y resumen.
- `VITE_API_BASE_URL` sin configurar ya no cae silenciosamente a localhost en producción:
  muestra "Falta configurar VITE_API_BASE_URL en el entorno de despliegue (Vercel)".
- Se retiró la instrumentación de diagnóstico del 404 (logs del navegador que exponían
  contenido de datos y `print` de rutas en el arranque de la API).

### Cambiado
- Log seguro de CORS en la API: si llega un `Origin` que no está en `ALLOWED_ORIGINS`
  se registra origen y ruta (nunca tokens) para diagnosticar despliegues sin adivinar.

## [0.4.0] — 2026-07-03 — Fase 3: Asistente IA

### Agregado
- **`POST /ai/summary`**: resumen ejecutivo automático del negocio + 4 preguntas sugeridas,
  generado desde las métricas del dashboard (Anthropic API **solo desde el backend**;
  modelo configurable con `ANTHROPIC_MODEL`).
- **`POST /ai/chat`**: chat anclado a los datos del negocio con respuesta en streaming (SSE).
- **Panel Asistente IA activo**: estados bloqueado → cargando → activo, resumen del periodo,
  preguntas sugeridas clickeables, historial de conversación e input con streaming.
- Cliente frontend `apiPostJson` + `apiStream` (lectura de SSE).

### Corregido
- **JWT de Supabase con firma ECC/P-256**: la API valida ES256/RS256 vía JWKS
  (`/auth/v1/.well-known/jwks.json`, claves cacheadas 5 min) además del HS256 legacy.
- Errores del servicio de IA ya no pierden los headers CORS: todo `/ai/summary` va envuelto
  en manejo de errores que devuelve HTTPException con detalle claro (503/4xx/500).
- Build de Render: se eliminó el pin explícito de `cryptography`.
- Persistencia best-effort del pipeline realmente best-effort (no bloquea si Supabase falla).

## [0.3.0] — 2026-07-03 — Fase 2: Resumen (dashboard)

### Agregado
- **Dashboard Resumen** completo (Recharts): 4 tarjetas KPI con variación vs mes anterior
  y sparklines (Ingresos, Ganancia Neta, Margen de Utilidad, Flujo de Caja), gráfico de
  evolución de ingresos/gastos/utilidad, Indicadores Clave, análisis por categoría con
  barras de margen, Estado Financiero con semáforo de Salud Financiera, donut de ventas
  por canal/sucursal, top 5 productos y proyección a 3 meses.
- **Selector de periodo funcional en el topbar**: "Todo el periodo" + cada mes con datos;
  filtra todo el dashboard y al entrar se auto-selecciona el último mes.
- **`/metrics` ampliado**: KPIs con variación vs el periodo anterior equivalente,
  gastos/utilidad/margen/flujo (si el archivo trae columna de costo), proyección a 3
  meses por crecimiento promedio acotado, filtro `date_from`/`date_to`, y ratios de
  balance declarados como no disponibles hasta conectar datos financieros.
- Rol `costo` en el mapeo automático de columnas.
- Paleta de series de gráficos validada (contraste, daltonismo) sobre las rampas de marca
  (`frontend/src/lib/charts.ts`).
- CSV de ejemplo ampliado a 3 meses (abril–junio 2026) con columna `Costo` (92 filas).

### Cambiado
- `frontend`: nueva dependencia `recharts`.
- Módulos `frontend/src/lib/` unificados con las versiones verificadas end-to-end
  (tras el fix de Vercel del `.gitignore` que excluía `lib/`).
- Tests de la API: 11 pruebas (nuevo shape de métricas + filtro de periodo).

### Corregido
- Variaciones de KPI ya no se calculan contra periodos no comparables: sin rango
  seleccionado quedan en null y la UI muestra "—".

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
