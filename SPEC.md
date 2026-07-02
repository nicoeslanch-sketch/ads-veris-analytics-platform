# SPEC — Plataforma de Análisis de Datos ADS Veris

> Especificación de referencia permanente. Toda decisión de producto, diseño y arquitectura
> debe ser consistente con este documento. No agregar features fuera de esta spec sin aprobación.

## 0. Rol y misión

Construcción incremental y por fases de la Plataforma de Análisis de Datos de ADS Veris:
un ERP simplificado + capa de análisis con IA, pensado para PyMEs chilenas.

Reglas de trabajo:

1. Antes de escribir código, leer el repositorio completo y confirmar su estado.
2. Proponer un plan de la fase actual y esperar aprobación antes de implementar.
3. Trabajar una fase a la vez. No adelantar funcionalidades de fases futuras salvo pedido explícito.
4. No agregar features, textos ni "mejoras" fuera de esta especificación sin preguntar primero.
5. Commits pequeños con mensajes claros. Nunca subir secretos al repo: usar `.env` y `.env.example`.
6. Ante opciones válidas, explicar el trade-off en 2–3 líneas y recomendar una; no bloquearse.

## 1. Contexto de negocio

ADS Veris es una empresa chilena que ofrece un pack de servicios para PyMEs, escalando así:

1. Planillas Excel (10 estándar + 1 personalizada).
2. Páginas web sencillas y de bajo costo.
3. Asesoría y diagramación de procesos.
4. **Esta plataforma de análisis de datos** — el destino final donde todos los servicios convergen.

Propuesta de valor central: *"Un analista de datos es muy costoso y contratar ingenieros no lo
puede permitir una PyME. Nosotros somos la solución."* La plataforma funciona como un analista
de datos siempre disponible: limpia los datos, los ordena, los muestra en un tablero claro y los
interpreta con IA para que el dueño del negocio tome mejores decisiones.

Flujo en una frase: el usuario sube su Excel → la plataforma (SQL + Python) lo estandariza y
limpia → los datos quedan cargados → se muestran como ERP con gráficos, tablas, indicadores y
ratios → un chat con IA anclado al negocio explica qué significa cada dato y sugiere qué hacer.

**Regla de flujo NO NEGOCIABLE**: si el usuario no ha cargado y limpiado datos, la plataforma
no muestra dashboard. Todo parte de los datos.

## 2. Stack técnico (prescriptivo)

- **Frontend**: React + Vite + React Router + TypeScript. Estilos con TailwindCSS (v4).
  Gráficos con Recharts. Íconos con lucide-react. Fuente Poppins (vía `@fontsource/poppins`).
- **Backend de datos / Auth / Storage**: Supabase (Postgres + Auth + Storage + Row Level Security).
- **Motor de datos (Python)**: microservicio FastAPI + pandas para estandarización, limpieza y
  cálculo de indicadores/ratios. Expuesto por HTTP. Deploy previsto: Render o Railway.
- **IA**: Anthropic API (Claude). Las llamadas se hacen **exclusivamente desde el backend
  FastAPI, nunca desde el frontend React**. Endpoints protegidos para: resumen automático,
  preguntas al asistente y limpieza personalizada. La API key vive solo en variables de entorno
  del backend (jamás en el navegador ni en el bundle del frontend). El modelo es configurable
  mediante la variable `ANTHROPIC_MODEL`; no hardcodear el nombre del modelo en el código.
- **Hosting**: Vercel (frontend), Render/Railway (API Python), Supabase (datos).
- Node 18+ / Python 3.11+.

### Seguridad de la API Python (obligatorio)

Todos los endpoints de FastAPI deben estar protegidos. El frontend enviará el JWT de Supabase
del usuario autenticado y FastAPI deberá validarlo antes de procesar datos, métricas o consultas
IA. Ningún endpoint sensible debe quedar público (solo `/health` es público).

### Flujo de archivos (obligatorio)

El usuario sube Excel/CSV desde el frontend **directamente a Supabase Storage**. Luego se guarda
metadata en `datasets`. FastAPI no debe recibir archivos grandes desde el navegador salvo casos
pequeños; idealmente procesa el archivo leyendo desde Supabase Storage mediante ruta segura o
signed URL.

### Variables de entorno (separación estricta)

Variables frontend permitidas (públicas, prefijo `VITE_`):

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_API_BASE_URL`

Variables backend secretas:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`

**Nunca usar `SUPABASE_SERVICE_ROLE_KEY` ni `ANTHROPIC_API_KEY` en React/Vite.**

### Despliegue del frontend en Vercel (proyecto Vite, no Next.js)

```
Framework / Preset: Vite
Root Directory:     frontend
Build Command:      npm run build
Output Directory:   dist
Install Command:    npm install
```

Si Vercel muestra `Other`, completarlo manualmente con esos valores. El servicio Python se
despliega aparte en Render/Railway.

## 3. Identidad de marca (tokens exactos)

```
--navy:      #1a3a52   (barra lateral, banner superior, textos de título)
--navy-deep: #12283a   (fondos oscuros / panel IA)
--teal:      #00a8a8   (acento principal, positivo, activo)
--gold:      #d4af37   (destacados, plan premium, CTA secundario)
--green:     #2fae7d   (valores positivos / éxito)
--coral:     #e8785a   (alertas / valores negativos)
--bg:        #ffffff con leve matiz claro para el área de trabajo
Tipografía:  Poppins (400/500/600/700/800)
```

Reglas visuales (consistencia obligatoria en TODOS los módulos):

- Barra lateral y banner superior: colores de marca (navy).
- Fondo del área de trabajo: blanco.
- Tarjetas, gráficos, tablas y viñetas: colores de marca sobre fondo blanco.
- Chat del Asistente IA: colores de ADS Veris.
- **No usar acentos morados ni paletas ajenas.** Donde las maquetas de referencia muestran
  morado, se reemplaza por el token de marca según el rol del elemento (CTA primario → teal/navy;
  premium → gold). Todo debe verse como un solo producto coherente.

## 4. Arquitectura de la app (shell común)

Layout fijo compartido por todas las pantallas:

- **Barra lateral izquierda**: logo "ADS Veris", navegación (Resumen, Explorar datos,
  Estandarización, Limpieza de datos, Historial, Conectores, Alertas, Reportes, Configuración),
  bloque "Fuentes conectadas" con estado, y bloque de ayuda al pie.
- **Barra superior**: selector de rango de fechas (filtra toda la pantalla), campana de
  notificaciones, menú de perfil.
- **Área central**: contenido del módulo.
- **Panel derecho — Asistente IA**: transversal, anclado a los datos cargados.

Rutas: `/login`, `/` (Resumen), `/explorar`, `/estandarizacion`, `/limpieza`, `/historial`,
`/conectores`, `/alertas`, `/reportes`, `/configuracion`. Rutas protegidas por auth de Supabase.

## 5. Modelo de datos (Supabase / Postgres — con migraciones)

Tablas mínimas:

- `profiles` — usuario, empresa, RUT, plan (`basico` | `gold`), preferencias (moneda, formato
  fecha, separador decimal, redondeo).
- `datasets` — archivo cargado (nombre, filas, columnas, fuente, estado, calidad %, fecha).
- `dataset_columns` — mapeo de columnas detectadas a un esquema normalizado (fecha, cliente,
  producto, categoría, monto, cantidad, canal, etc.).
- `cleaning_jobs` — reglas aplicadas, problemas detectados/corregidos, "antes/después".
- `analyses` — análisis guardados desde Explorar datos.
- `alerts` y `alert_rules` — alertas generadas y reglas configuradas por el usuario.
- `activity_log` — registro de toda la actividad (para Historial).
- `connectors` — fuentes conectadas y estado de sincronización.

Aplicar Row Level Security: cada usuario solo ve sus propios datos.

## 6. Motor Python (FastAPI + pandas)

Endpoints mínimos (todos protegidos con JWT de Supabase):

- `POST /standardize` — recibe el archivo/dataset; unifica nombres y textos duplicados,
  estandariza fechas y números, normaliza mayúsculas/minúsculas/tildes. Devuelve preview +
  resumen de cambios.
- `POST /clean` — detecta y corrige: duplicados, valores nulos, formatos de fecha inválidos,
  textos inconsistentes, tipos de dato incorrectos, columnas vacías, valores fuera de rango.
  Recibe qué reglas están activas.
- `POST /clean/custom` — (solo plan Gold) recibe instrucciones del usuario en lenguaje natural /
  parámetros y aplica limpieza personalizada dentro de un conjunto acotado de reglas (catálogo
  limitado y validado de operaciones; no variables infinitas).
- `POST /metrics` — a partir del dataset limpio y el mapeo de columnas, calcula los indicadores
  y ratios (ver sección 7).

Devolver siempre un objeto claro con datos + metadatos (qué se cambió, cuántas filas, calidad
estimada).

## 7. Módulos ([MVP] / [Posterior])

### Resumen — Panel principal [MVP]

Tarjetas KPI: Ingresos Totales, Ganancia Neta, Margen de Utilidad, Flujo de Caja (cada una con
variación vs. periodo anterior y mini-tendencia). Gráfico "Evolución de Ingresos, Gastos y
Utilidad". Bloque "Indicadores Clave": ROA, ROE, Ratio de Liquidez Corriente, Rotación de
Inventario, Días de Cobro, Días de Pago, Prueba ácida. Tabla "Análisis por Categoría". "Estado
Financiero" (Activos, Pasivos, Patrimonio, Capital de Trabajo, semáforo de Salud Financiera).
Donut "Ventas por Canal". "Top Productos/Servicios". "Proyección" a 3 meses. Todo filtrado por
el rango de fechas superior.

### Conectores — Fuentes de datos [MVP: carga de archivo] / [Posterior: integraciones]

Carga de Excel/CSV en el MVP. Después: conectores a Google Sheets, SQL/MySQL, Supabase, etc.,
con estado y sincronización.

### Estandarización [MVP]

Zona de carga, explicación "¿Qué hace?", proceso en 3 pasos, archivos recientes, nota de
seguridad. Llama a `POST /standardize`.

### Limpieza de datos [MVP]

Encabezado (archivo actual, filas, columnas, calidad %, estado). Pasos: Cargar → Revisar
problemas → Configurar reglas → Aplicar → Dataset limpio. Vista previa "antes de la limpieza"
resaltando errores. Lista de problemas detectados. "Qué se corregirá". Reglas activas (toggles).
Panel derecho: Limpieza personalizada con IA (Premium/Gold) con chat y cupo de prompts según
plan. Botón "Aplicar limpieza y continuar" que deja el dataset cargado para el resto de módulos.

### Explorar datos [MVP básico] / [Posterior: mapa, distribución avanzada]

"¿Qué quieres descubrir hoy?" (análisis predefinidos), "Define tu análisis" (rango, comparar
con, agrupar por, filtros), "Hallazgos principales" con gráfico y detalle, "Profundiza"
(tabla/tendencia), "Recomendación inteligente" con plan de acción. Guardar/compartir análisis.

### Alertas — Sistema de aviso temprano [Posterior, tras MVP]

Vigilancia automática, preventiva no solo descriptiva. 4 bloques: Alertas activas, Resueltas,
Reglas de alerta, Historial. Cada alerta responde: qué pasó, cuándo, severidad, área afectada,
recomendación. Panel derecho: resumen por severidad y por área. El usuario define reglas (ej.:
avisar si ventas bajan >10%, si un cliente supera cierto % del total, si el margen cae bajo un
nivel).

### Historial [Posterior]

Trazabilidad total: cargas, limpiezas, estandarizaciones, análisis, consultas al chat,
recomendaciones. Detalle con "antes/después". Permite re-ejecutar una limpieza anterior.

### Reportes [Posterior]

Generar y descargar reportes (PDF/Excel) del dashboard, indicadores y análisis.

### Configuración [MVP: perfil + preferencias / Posterior: usuarios, facturación]

Perfil y cuenta (nombre, correo, empresa, RUT, zona horaria, idioma), logo y apariencia,
preferencias de datos (moneda CLP, formato de fecha, separador decimal, tratamiento de nulos,
redondeo). Estado de la cuenta (plan, usuarios, almacenamiento, consultas IA usadas).

## 8. Asistente IA (el diferenciador) [MVP tras dashboard]

Panel derecho anclado a los datos limpios del negocio. Debe:

- Generar un resumen automático al cargar/actualizar datos.
- Ofrecer sugerencias proactivas y preguntas por defecto clickeables.
- Permitir preguntas libres por chat.
- Entregar lectura + recomendación, no solo describir. Tono esperado:
  - "No estás vendiendo casi nada del Producto X hace meses; convendría evaluar sacarlo e
    invertir más en el Producto Y."
  - "La prueba ácida está en un valor alto → exceso de efectivo; podrías reinvertir. En el caso
    contrario, indicaría problemas para cumplir obligaciones tributarias o de deuda."

Implementación: el frontend envía la pregunta + un contexto compacto de los datos/indicadores
calculados a un endpoint del servidor, que llama a la Anthropic API con un system prompt que
fije el rol ("analista de datos para una PyME chilena, directo y práctico") y devuelva
interpretación + recomendación. Cada consulta descuenta del cupo del plan.

## 9. Planes y feature gating

- **Plan Básico**: dashboard, limpieza automática, análisis, consultas IA limitadas.
- **Plan Gold**: todo lo anterior + limpieza personalizada (instrucciones propias, dentro del
  catálogo acotado de reglas) + muchas más consultas IA.

Gating por `profiles.plan` y contador de consumo (prompts/consultas). Las funciones bloqueadas
muestran un CTA "Mejorar plan".

## 10. Localización (Chile)

- Idioma español (es-CL) en toda la UI.
- Moneda CLP por defecto, con formato `$24.350.000` (punto de miles).
- RUT como identificador de empresa (opcional).
- Formato de fecha DD/MM/YYYY, separador decimal coma, zona horaria America/Santiago.
- Todo configurable en Configuración y respetado por el motor de métricas.

## 11. Roadmap por fases

- **Fase 0 — Scaffold + marca + shell.** Proyecto Vite+React+Tailwind, tokens de marca, Poppins,
  layout (sidebar + topbar + panel IA vacío), routing, auth Supabase (login/registro),
  `.env.example`, README con setup.
- **Fase 1 — Pipeline de datos.** Motor Python (standardize/clean/metrics), módulos
  Estandarización y Limpieza conectados, guardar dataset limpio en Supabase. Datos de ejemplo.
- **Fase 2 — Resumen (dashboard).** KPIs, ratios e indicadores calculados desde el dataset
  limpio, con gráficos Recharts. Regla "sin datos, no hay dashboard".
- **Fase 3 — Asistente IA.** Resumen automático + chat anclado a los datos + preguntas
  sugeridas + gating de consultas.
- **Fase 4 — Explorar datos.** Análisis guiados, hallazgos, recomendación.
- **Fase 5 — Alertas, Historial, Conectores, Reportes, Configuración avanzada y planes.**
