# Changelog — ADS Veris Plataforma de Análisis de Datos

Formato: [Keep a Changelog](https://keepachangelog.com/es/). Fases según [`SPEC.md`](./SPEC.md).

## [0.8.1] - 2026-07-08 - Examen de calidad post-Fase 7

### Corregido
- **Caché del pipeline redimensionado para Render free (512 MB)**: de 4 entradas ×
  1,5M celdas (podía superar la RAM del plan) a 3 × 600k celdas (~150 MB peor caso).

### Agregado
- **Indicadores Clave del Resumen ahora son operativos y reales**: Ticket promedio,
  Transacciones, Unidades vendidas, Mejor mes, Crecimiento del periodo, Tendencia
  mensual y Margen — calculados de los datos del archivo (la pared de "—" de ROA/ROE
  pasó a una nota compacta hasta conectar datos de balance).
- **Línea de promedio de ingresos** en el gráfico de evolución (lectura instantánea:
  sobre/bajo el promedio del periodo).
- **Reporte de calidad con muestras de valores problemáticos** (hasta 3 por columna,
  fechas inválidas y tipos incorrectos): el insumo exacto que necesitará el refinado
  IA para "terminar el 20%" sin re-leer el archivo.

### Verificado (examen de calidad)
- 57 tests de la API en verde, build de producción OK y E2E Playwright completo:
  pipeline, limpieza dirigida por variables (aplicada de verdad), descarga de base
  limpia .xlsx con celdas marcadas, página Planes y dashboard.
- `/metrics` maneja correctamente los nulos preservados (dropna en todos los
  agregados) — el cambio de no-imputación es seguro para los KPIs.

## [0.8.0] - 2026-07-07 - Fase 7: Planes, limpieza dirigida y motor profesional

### Agregado
- **Modelo de tres planes** (`basico | analista | gold`): migración `0008` renombra los
  `gold` legacy a `analista`; Gold pasa a ser el tercer plan "en construcción" (conexión
  a bases SQL + comunidad). Matriz única de capacidades en `api/app/capabilities.py`,
  espejada en `frontend/src/lib/plans.ts`.
- **Interruptor global `PLAN_ENFORCEMENT`** (backend) + `VITE_PLAN_ENFORCEMENT`
  (frontend), **apagado en Fase 7**: todo accesible para probar, con cada puerta ya
  instalada (403/candados listos para encender sin tocar componentes).
- **Página Planes** (`/planes`, nuevo ítem del sidebar): 3 tarjetas con sus features
  desde la matriz única, Gold con badge "En construcción" (SQL + comunidad), y sección
  **"Tokens de limpieza dirigida (addons)"** con el cupo del mes, el saldo de tokens y
  el botón **"Solicitar más"** (`POST /addons/request` → tabla `addon_requests`; ADS
  Veris contacta al usuario).
- **Limpieza dirigida por variables** (`POST /clean/assisted`, planes Analista/Gold):
  chat horizontal en la parte inferior de Limpieza — el usuario escribe qué columnas y
  reglas quiere ("limpia Fecha y Ventas, no toques Cliente") y un segundo botón
  **"Limpiar con mis variables"** corre el motor dirigido. **2 intentos base al mes**
  (`AI_CLEANING_MONTHLY_LIMIT`) + **tokens addon** (ledger `plan_addons`, migración
  `0009`): advertencia visible de intentos, 429 con CTA a Planes al agotarse, y 422
  SIN consumir el intento si las instrucciones no se reconocen.
- **Costuras IA preparadas y APAGADAS** (un solo `# TODO IA` cada una):
  `interpret_cleaning_instructions` (hoy determinista: columnas + catálogo acotado de
  reglas) y `refine_with_ai` (paso final opcional del pipeline, flag
  `AI_REFINE_ENABLED=false`). Activar la IA será reemplazar el cuerpo, no el pipeline.
- **`POST /admin/grant-credits`** (solo `profiles.is_admin`, migración `0008`): otorga
  tokens a mano insertando en el ledger `plan_addons` (alternativa por SQL documentada
  en el README). **`GET /plans/usage`**: cupos de insights + limpieza + addons.
- **Mapeo de columnas editable** (§5.10): tarjeta en Limpieza para corregir el rol de
  cada columna; lo respetan `/clean`, `/clean/assisted`, `/clean/download` y `/metrics`
  (en toda la app vía `DatasetContext`), con persistencia best-effort en
  `dataset_columns` (policy de update en `0008`).
- Tests de la API: **57 pruebas** (24 nuevas: matriz y enforcement on/off, cupo de
  limpieza 429/addons, `/clean/assisted` dirigido/422/429, `/plans/usage`,
  `/addons/request`, `/admin/grant-credits`, y las mejoras del motor).

### Motor de datos — mejoras profesionales (§5)
- **Los nulos numéricos ya NO se imputan con 0** (§5.1): una venta faltante que se
  volvía $0 sesgaba sumas, promedios y márgenes. Ahora quedan vacíos (NaN para
  `/metrics`), catalogados por columna y marcados en la descarga. La calidad
  post-limpieza mide problemas estructurales pendientes; los nulos preservados por
  diseño quedan en el reporte de calidad.
- **Outliers IQR solo en roles métricos** (monto/costo/cantidad, §5.3): nunca sobre
  IDs, RUT, folios ni años.
- **Duplicados con criterio explícito** (§5.2): detección por fila completa
  normalizada + **advertencia** cuando el archivo no trae columna identificadora
  (dos ventas legítimamente idénticas no se pueden distinguir — se avisa en vez de
  borrar en silencio; se optó por advertir sobre la clave de negocio del spec porque
  una clave parcial borraría MÁS ventas legítimas, no menos).
- **Detección de tipo con muestra aleatoria determinista + confianza por columna**
  (§5.4): un archivo ordenado ya no misclasifica.
- **Convención numérica por columna** (§5.5): "850.000" se decide por consistencia de
  toda la columna (miles es-CL vs decimal), no celda a celda.
- **Fechas con formato dominante por columna** (§5.6): `dayfirst` detectado (no fijo)
  y soporte de meses en texto ("01 mayo 2026", "1 de junio de 2026").
- **Caché del pipeline** (§5.7): cambiar el periodo del dashboard ya no re-estandariza
  ni re-limpia el archivo (LRU por hash de contenido + reglas + mapeo, con tope de
  celdas para proteger la memoria de Render).
- **Fuzzy matching de typos** (§5.11): "Santigo" → "Santiago" con Levenshtein acotado
  y guardas (frecuencias, longitud, misma inicial) para no fusionar valores legítimos.
- **Excel multi-hoja y filas de título** (§5.12): se elige la hoja con más datos (con
  aviso de las omitidas) y se detecta la fila real de encabezados; separador CSV
  decidido con varias líneas.
- **Reporte de calidad por columna** (§5.9): rol, tipo + confianza, nulos y %,
  inválidos, outliers y convención — visible en la respuesta y listo para alimentar
  el refinado IA.
- Detección vectorizada de nulos y parseos por columna calculados una sola vez (§5.8).

### Cambiado
- **El panel Asistente IA solo vive en Resumen y Explorar datos** (Fase 7 §4): salió
  del `AppShell` global; en el resto de pantallas el contenido usa todo el ancho.
- Botones de Limpieza según el diseño de Fase 7: **"Limpiar datos"** (reglas por
  defecto, todos los planes) arriba, y **"Limpiar con mis variables"** junto al chat.
- La clave `correcciones.valores_nulos_a_reemplazar` pasó a
  `valores_nulos_normalizados` (los nulos se señalizan, no se reemplazan).
- Cuota de insights y de limpieza separadas por `kind` en `ai_usage` (los intentos de
  limpieza no gastan el cupo del asistente y viceversa). Nueva variable
  `AI_MONTHLY_LIMIT_ANALISTA` (la `_GOLD` queda para el plan Gold).
- Configuración muestra también el contador de limpieza dirigida + tokens y enlaza a
  Planes; Reportes gatea sus descargas con `download_reports` (candado + CTA cuando
  el enforcement esté encendido).

### Corregido
- `dataset_columns` no aceptaba el rol `costo` (detectado desde la Fase 2): el check
  se corrige en la migración `0008`.

## [0.7.2] - 2026-07-05 - Microfase 6.2: preparacion comercial

### Agregado
- Matriz de capabilities por plan: Basico mantiene carga, limpieza, dashboard e IA; Analista
  habilita descarga de base limpia, limpieza avanzada, variables custom y reportes avanzados.
- Nuevo `POST /clean/download`: aplica limpieza y devuelve CSV/XLSX solo si el usuario tiene
  capability `download_clean_dataset` (Plan Analista). El bloqueo vive en backend.
- Export de base limpia neutraliza formula injection (`=`, `+`, `-`, `@`) solo en la copia
  descargable; el dataset interno no se modifica.

### Cambiado
- La UI muestra el plan comercial como "Analista" sin migrar todavia el valor interno `gold`.
- Historial muestra la fuente de cada dataset (`Excel / CSV` o `Google Sheets`).
- Reportes leen `profiles.company` como fuente principal de empresa.

### Corregido
- Fallos de `activity_log` ya no hacen fallar `markStandardized()` ni `saveCleaningJob()`.

## [0.7.1] - 2026-07-04 - Microfase 6.1: estabilidad de Conectores e Historial

### Corregido
- "Historial de cargas" en Limpieza ahora navega a `/historial`.
- `markStandardized()` revisa errores de Supabase y avisa suavemente si no pudo guardar
  todo el detalle de historial/columnas.
- Importaciones desde Google Sheets quedan registradas con `source = 'google_sheets'`.
- Retomar un dataset limpio usa las reglas reales del ultimo `cleaning_job` cuando existen.

### Seguridad y robustez
- `POST /connectors/sheets` limita la URL a 2000 caracteres.
- El nombre de archivo devuelto por Google Sheets se sanitiza y recorta antes de llegar al
  navegador.

## [0.7.0] — 2026-07-05 — Fase 6: Conectores + endurecimiento de reportes y persistencia

### Agregado
- **Conector Google Sheets (funcional)**: el usuario pega el enlace de una hoja pública o
  compartida por enlace y entra al mismo pipeline que un archivo subido. Nuevo
  `POST /connectors/sheets`: la API extrae el ID del documento y arma ella la URL oficial
  de export (nunca descarga la URL cruda — sin SSRF), tope de 15 MB, detección de hoja
  privada con instrucción clara ("Compartir → Cualquier persona con el enlace") y nombre
  real del archivo desde Content-Disposition.
- **Página Conectores completa**: Google Sheets (disponible), Excel/CSV (enlace a
  Estandarización), base de datos SQL y otras integraciones (próximamente).
- **Hook compartido `useFileImport`**: Estandarización y Conectores usan el mismo flujo
  (Storage + datasets + /standardize) sin lógica duplicada.
- Tests de la API: **27 pruebas** (conector: URL inválida, hoja privada, import feliz,
  requiere token; guard de tamaño de métricas 413).

### Seguridad
- **Reporte PDF**: todo valor que viene de los datos del usuario (productos, categorías,
  canales, empresa, archivo) se escapa como HTML antes de entrar a la vista imprimible.
- **Export CSV**: celdas que empiezan con `=`, `+`, `-` o `@` se neutralizan con `'`
  (formula injection de Excel).
- **`/ai/*` rechaza contextos de métricas gigantes** (413 sobre 200 KB): el prompt ya
  estaba acotado por campos conocidos, esto frena el abuso directo del endpoint.

### Corregido
- **`saveCleaningJob` es best-effort de verdad**: sus errores (RLS, migración faltante,
  red) ya no pueden mostrarse como "No se pudo aplicar la limpieza" — la limpieza queda
  aplicada y la UI avisa suave "no se pudo guardar en el historial". Además ahora sí
  revisa los errores que devuelve supabase-js (antes se ignoraban en silencio).
- **Historial distingue error de vacío**: un fallo de Supabase muestra "No se pudo cargar
  el historial" en vez de "Todavía no hay actividad".
- **Retomar restaura el estado limpio**: si el dataset estaba `limpio`, re-aplica la
  limpieza y te deja directo en el Resumen (antes obligaba a rehacer el flujo).
- **Reglas de alertas por usuario** (`localStorage` con key por `user.id`): en un
  computador compartido ya no se heredan los umbrales de otra cuenta.
- `record_usage` registra el status HTTP cuando `ai_usage` responde error (típico:
  migración 0006 sin ejecutar) — antes fallaba en silencio.
- El botón "Historial de estandarizaciones" ahora navega a Historial (estaba muerto).

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
