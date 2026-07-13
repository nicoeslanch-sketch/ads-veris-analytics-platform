# Changelog — ADS Veris Plataforma de Análisis de Datos

Formato: [Keep a Changelog](https://keepachangelog.com/es/). Fases según [`SPEC.md`](./SPEC.md).

## [0.13.0] - 2026-07-13 - Fase 12, Bloque 1: duplicados no destructivos

Este bloque cambia deliberadamente la política de seguridad del motor: los
duplicados se detectan siempre, pero **no se eliminan por defecto**. La acción
"Eliminar duplicados exactos" requiere una confirmación explícita del usuario;
solo elimina repeticiones exactas del archivo original. Las coincidencias que
aparecen únicamente después de normalizar permanecen como candidatas a revisión.

### Motor y trazabilidad
- Se separaron los duplicados exactos originales, los normalizados adicionales,
  los conflictos de ID y las advertencias de posible granularidad omitida. Estas
  categorías son mutuamente excluyentes y no se suman como si midieran lo mismo.
- La taxonomía de identificadores distingue fila, documento, entidad y atributo.
  Ningún nombre de columna ni heurística autoriza borrados automáticamente.
- La exclusión estadística de RUT, teléfonos, códigos, SKU, años, folios e índices
  quedó independiente de la política de duplicados, preservando la protección IQR.
- El loader conserva por metadatos la fila física original y la hoja de origen,
  sin contaminar las columnas del usuario. El preview y la hoja `Observaciones`
  usan esa referencia real.
- `/clean`, `/clean/assisted`, `/clean/download` y `/metrics` aceptan el campo
  aditivo `eliminar_duplicados`, con default seguro `false`; la decisión también
  forma parte de la clave de caché.

### Frontend y persistencia
- Limpieza muestra un diagnóstico prominente y una acción coral independiente,
  seguida de un modal de riesgo con cancelar enfocado por defecto.
- La limpieza dirigida no puede autorizar el borrado mediante texto libre.
- La opción elegida se propaga a métricas, IA, descarga y restauración de sesión.
- Nueva migración `0012_cleaning_job_options.sql` para persistir la decisión en
  `cleaning_jobs.options`. No se aplica automáticamente al proyecto remoto.

### Verificación
- Fixture sintético específico para cada conducta de seguridad y script local
  `scripts/regresion_req5325.py` para auditar el archivo real sin versionarlo.
- Regresión REQ5325: 14.917 filas por defecto; 14.324 únicamente tras confirmar
  la eliminación de sus 593 repeticiones exactas.

## [0.12.0] - 2026-07-11 - Fase 11: Rendimiento con datos grandes, motor más preciso y continuidad de sesión

La lentitud reportada con bases de >50.000 filas tenía una causa raíz medible:
el caché del pipeline excluía los archivos grandes, así que CADA módulo
(Limpieza, Resumen, Explorar, IA, Alertas, Reportes) reprocesaba el archivo
completo desde cero; además la estandarización parseaba celda por celda.
Benchmark 50.000×8: estandarizar+limpiar pasó de ~13,3 s a **~1,8 s** y los
módulos siguientes salen del caché en ~0,3 s.

### Rendimiento (archivos grandes)
- **Caché por presupuesto de celdas**: ya no hay lista de exclusión por tamaño —
  el caché admite hasta 2,4 M de celdas TOTALES con desalojo LRU, así el archivo
  grande (el que más lo necesita) también se cachea. "Retomar" desde Historial y
  cambiar de módulo dejan de reprocesar el pipeline completo.
- **Parseo por valores únicos** (`map_unique`): fechas, números y textos se
  parsean una vez por valor distinto (50.000 filas suelen tener <2.000 valores
  únicos) en estandarización, limpieza y métricas.
- **Loader vectorizado**: la detección de filas vacías al final del archivo dejó
  de recorrer fila por fila.
- **Retomar sin descarga**: Historial ya no baja el archivo al navegador; todas
  las llamadas van por `storage_path` y el backend lo lee directo de Storage.

### Motor más preciso (menos errores de estandarización/limpieza)
- **Números US**: `1,234.56` y `1,234,567` ahora se parsean (regla universal:
  el ÚLTIMO separador es el decimal); convivencia es-CL/US en la misma base.
- **Fechas con evidencia por valor**: en una columna que mezcla DD/MM y MM/DD,
  cada valor inequívoco (13/05, 05/14) se interpreta por su propia evidencia y
  las ambiguas usan la convención dominante **con aviso visible** al usuario.
- **Variantes morfológicas**: "pagada"→"pagado", "boletas"→"boleta" en
  categóricas de baja cardinalidad, con guardas conservadoras (≤30 categorías,
  misma raíz, solo vocal final a/o o plural 's', minoría ≤ ¼ de la dominante —
  categorías equilibradas jamás se fusionan).
- **Mapeo parcial fusionado** (`resolve_mapping`): corregir UNA columna en
  Limpieza ya no borra el resto del mapeo automático en /metrics (antes el
  dashboard podía quedar en $0 tras asignar una sola columna).

### Frontend confiable
- **Timeouts con reintento**: las llamadas al pipeline se cancelan a los 240 s
  (90 s JSON, 60 s GET) con mensaje claro, y Resumen/Explorar muestran botón
  **"Reintentar"** — antes un fallo dejaba la página vacía para siempre porque
  la clave de fetch quedaba marcada como "ya pedida".
- **Claves de recálculo completas**: cambiar el mapeo de columnas o la hoja
  refresca Resumen, Explorar y las métricas compartidas (Alertas/Reportes/IA).
- **Moneda activa real**: los montos se formatean con la moneda detectada por el
  backend (`US$`, `€`, `$`) en toda la sesión — una base USD ya no se muestra
  como pesos chilenos.
- **Resumen sin monto**: si ninguna columna se reconoce como ventas/monto, el
  dashboard muestra una guía para asignarla en el mapeo (antes: puro $0).
- Cambio de hoja fallido revierte a la hoja anterior (el contexto jamás apunta
  a una hoja que no se procesó).

### Continuidad de sesión
- **Restaurar último trabajo**: al iniciar sesión con la sesión vacía, la
  plataforma retoma automáticamente el dataset más reciente del Historial
  (indicador "Restaurando tu último trabajo…" + opción "Empezar con otro
  documento"). La retención de Storage también corre al iniciar sesión.
- **"Estandarizar nuevo documento"**: banner explícito en Estandarización con
  el dataset activo ([Continuar] / [Estandarizar nuevo documento]) y enlace
  "Procesar otro archivo" en Limpieza — cada documento nuevo crea su registro
  en el Historial y el anterior queda guardado para retomar.

### Contacto
- **WhatsApp, Instagram y correo** en el bloque de ayuda del sidebar y en el
  modal de soporte: wa.me/56983894129, instagram.com/adsveris y
  servicios@adsveris.com.

### Verificación
- 129 pruebas backend (12 nuevas de Fase 11: convenciones numéricas, fechas
  mixtas con aviso, pagado/pagada con guarda de equilibrio, mapeo parcial,
  caché reutilizado entre módulos, `map_unique` ≡ `map`), build de producción
  y E2E completo (pipeline + contactos + banner de continuidad + moneda).

## [0.11.0] - 2026-07-09 - Fase 10: Endurecimiento comercial — seguridad, exactitud financiera y responsive

Triage crítico del informe de calidad externo: se tomó lo que endurece el
producto (P0 de seguridad, exactitud financiera, motor más conservador,
responsive) y se pospuso con registro lo que exige refactors de riesgo
(cuotas atómicas por RPC, persistencia transaccional, paginación admin).

### Seguridad (P0)
- **Migración `0011`**: se revoca el UPDATE de `authenticated` sobre profiles y
  se otorga POR COLUMNA solo sobre los campos de contacto. Antes, cualquier
  usuario autenticado podía llamar directo a la REST API de Supabase y ponerse
  `plan='gold'` + `is_admin=true` en su propia fila (la RLS lo permitía porque
  la fila era suya). **Ejecutar antes de aceptar usuarios externos.**
- Bootstrap admin robusto: `/admin/*` acepta también al correo `ADMIN_EMAIL`
  (verificado por Supabase Auth) aunque `is_admin` aún no esté marcado.
- Validación estricta de `rules`/`mapping`/`scope` (claves y tipos → 422),
  límites de tamaño en los inputs de IA (pregunta 2000, historial 12×4000,
  roles solo user/assistant) y errores de IA/stream **sin detalles internos**
  (código de incidente al cliente, detalle a los logs).
- Anti-abuso de soporte: máximo 3 solicitudes pendientes por usuario, sin
  duplicados idénticos pendientes (429/409); solicitudes de tokens/upgrade sin
  duplicados pendientes del mismo tipo.
- `/admin/grant-credits` ahora audita en `admin_audit` igual que los cambios
  de plan.

### Exactitud financiera
- **Cobertura de costos**: utilidad y margen se calculan SOLO sobre las filas
  con ingreso Y costo (antes los costos faltantes actuaban como $0 e inflaban
  la ganancia). `kpis.cobertura_costos` + advertencia visible cuando es parcial.
- **Nombres honestos**: "Ganancia Neta" → **Utilidad Bruta**, "Flujo de Caja" →
  **Resultado del Periodo**, "Margen de Utilidad" → **Margen Bruto** (venta −
  costo directo no es ganancia neta ni caja).
- **Moneda real**: detección por tokens en los montos CRUDOS (US$, USD, €, CLP);
  `moneda` deja de estar fija en CLP, y una base con monedas mezcladas recibe
  advertencia explícita ("los totales suman sin convertir"). La IA recibe la
  moneda y las advertencias en su contexto.
- **"vs mes anterior" de verdad**: un mes calendario completo se compara con el
  mes calendario anterior (mayo vs abril), no con una ventana de 31 días que
  arrastraba el 31 de marzo.
- **Fix de contexto**: Alertas y Reportes ya no heredan en silencio el mes que
  el usuario estaba mirando en el Resumen — el contexto solo cachea métricas
  del periodo completo.

### Motor más conservador (jamás romper datos)
- **Fuzzy jamás en identificadores**: SKU/folio/RUT/email/teléfono quedan fuera
  de la fusión por Levenshtein ("SKU-100I" ya no se fusiona con "SKU-1001");
  categorías y ciudades siguen corrigiéndose.
- **Duplicados seguros**: con columna ID se mantiene el criterio normalizado
  (seguro); SIN columna ID solo se eliminan filas 100% idénticas y las "casi
  idénticas" quedan como `duplicados_probables` con aviso — nunca se borra una
  venta real por diferencias de formato.
- **Scope dirigido estricto**: instrucciones que excluyen todas las columnas →
  422 sin consumir el intento (antes un alcance vacío se reinterpretaba como
  "todas las columnas").
- **Descarga limpia de verdad** (§6.5): el Excel ya no escribe "SIN MONTO" ni
  "FECHA INVALIDA" DENTRO de los datos — hoja `Datos_limpios` intacta (celdas
  vacías + colores) + hoja **`Observaciones`** con fila/columna/detalle. El CSV
  sale limpio, importable en cualquier sistema.
- **Carga endurecida**: `.xls` antiguo rechazado con mensaje claro (la UI ya no
  lo promete), y guardia anti ZIP-bomb en `.xlsx` (expansión máxima y ratio de
  compresión) antes de tocar pandas.
- **Selector de hoja**: si el Excel trae varias hojas, Estandarización muestra
  chips para elegirla (parámetro `sheet` en todo el pipeline + caché);
  cambiarla recalcula limpieza y dashboard.
- **Diccionario auditado** (§7.1): 60 entradas "numero de boleta/factura/orden/…"
  reclasificadas de `cantidad` a identificador (un folio jamás se suma como
  unidades); "numero de ventas" (plural, conteo) sigue siendo cantidad. Test de
  CI: ningún identificador puede apuntar a monto/costo/cantidad.

### Responsive y UX
- **Sidebar móvil**: hamburguesa en el topbar + cajón deslizante (< lg).
- **Asistente IA sin consumo oculto** (§9.1): el panel SOLO se monta cuando es
  visible — en pantallas chicas vive tras un botón flotante que abre un drawer;
  el resumen IA se genera al abrirlo (una vez) y jamás gasta cupo escondido.
- **Recuperar contraseña** en el Login (enlace por correo de Supabase) y mínimo
  de 8 caracteres al registrarse.
- ProtectedRoute con guardia de producción: sin variables de Supabase la app
  muestra "Configuración incompleta" en vez de abrirse sin sesión.
- El plan del usuario se refresca al volver el foco a la pestaña (si el admin
  activó un plan, se ve sin recargar).
- El modal de ayuda muestra **"Mis solicitudes"** con estado y la respuesta del
  equipo, y el texto ya no promete correo (aún no hay envío transaccional).
- Copys honestos: privacidad de Estandarización (qué se almacena y qué recibe
  la IA), Alertas ("se evalúan al abrir la página", no "vigilancia automática").

### Operación
- `requirements.txt` con **versiones fijadas** (despliegues reproducibles).
- **CI en GitHub Actions**: pytest (motor + seguridad + auditoría del
  diccionario) y build del frontend con chequeo de tipos en cada push/PR.
- Retención: la desvinculación de datasets purgados verifica el status HTTP.

### Verificado
- **118 tests de la API** (21 nuevos de Fase 10), build de producción OK, y
  E2E Playwright x2: pipeline completo con nombres honestos + descarga con
  Observaciones, y recorrido móvil (hamburguesa, drawer IA, sin errores de
  consola).

### Pendiente registrado (no tomado a propósito)
- Cuotas atómicas por RPC SQL, persistencia transaccional del pipeline,
  paginación del panel admin, correo transaccional de soporte, benchmark F1
  del diccionario, XLSX/PDF de reportes generados en backend, retención por
  cron: refactors de mayor riesgo que no bloquean la operación inicial y
  quedan para la Fase 11 (ver PHASE_STATUS).

## [0.10.0] - 2026-07-09 - Fase 9: Mapeo universal — diccionario de roles y biblioteca de prompts IA

### Agregado
- **Diccionario universal de roles** (`api/app/data/palabras_clave_roles.csv`):
  ≈15.600 palabras clave normalizadas únicas, **64 roles en 12 grupos** (tiempo,
  dinero, cantidad, identificadores, entidades, catálogo, ubicación, contacto,
  clasificación, texto libre, RRHH, bancario), en español chileno e inglés, con
  abreviaturas reales (fec_emision, cxc, qty), términos locales (RUT, DTE, glosa,
  comuna, AFP, UF) y compuestos/plurales legítimos. Columnas: palabra_clave, rol,
  grupo, tipo_dato, idioma, prioridad y `rol_motor_actual` (equivalencia segura
  con los 10 roles del motor de métricas).
- **Motor de matching** (`api/app/engine/dictionary.py`): match del encabezado en
  4 etapas — exacto → contención por TOKENS ("fecha de emision" dentro de "Fecha
  de Emisión DTE", sin falsos positivos por substring) → prefijo/sufijo
  ("FechaVenta2026") → fuzzy Levenshtein acotado ("Montto" → monto). Empates por
  largo de clave y `prioridad`. Carga lazy única + memoización: costo ~0 por request.
- **`detect_column_roles` en dos pasadas** (`mapping.py`): (1) diccionario —
  gana la columna con mejor match cuyo rol extendido tiene equivalencia segura
  con el motor; (2) **compatibilidad legacy** — las palabras clave históricas
  rellenan los roles que queden vacíos. Resultado: "Total Neto" le gana el rol
  monto a "Precio Unitario" (que ya no se suma como ingreso), pero un archivo
  cuyo único campo de dinero es "Precio" sigue funcionando igual que siempre.
- **Mapeo extendido visible**: `/standardize` devuelve `mapeo_extendido` (rol de
  64, método y confianza por columna) y el `reporte_calidad` de `/clean` incluye
  `rol_extendido`, `grupo_rol` y `match_diccionario` por columna — insumo directo
  del refinado IA (§5.13) y de la tarjeta de mapeo de Limpieza.
- **Biblioteca de prompts** (`api/app/data/prompts_estandarizacion_por_rol.txt` +
  `engine/prompt_library.py`): prompt de sistema, clasificador de columnas sin
  match ([PROMPT B]), 12 prompts de grupo con catálogo acotado por rol (nunca
  imputar 0 en dinero, nunca fusionar clientes distintos, RUT inválido se marca)
  y el prompt de refinado global ([PROMPT C] = interfaz de `refine_with_ai`).
  Parseo lazy por secciones, `prompt_for_role(rol)` resuelve el grupo vía el CSV
  y `fill()` rellena las variables de plantilla.
- **Costura IA del clasificador** (`engine/ai_classifier.py`, flag
  `AI_CLASSIFIER_ENABLED=false`): cuando el diccionario no reconoce un encabezado,
  la IA lo clasificará dentro de la MISMA taxonomía cerrada usando nombre +
  muestra de valores. Preparada y APAGADA, con un único `# TODO IA` — mismo
  criterio que las costuras de la Fase 7.
- Tests: **97 pruebas** (17 nuevas: carga del diccionario, las 4 etapas de match,
  falsos positivos por substring, roles extendidos sin motor, dos pasadas de
  mapeo, compatibilidad histórica, mapeo_extendido en la API, reporte de calidad,
  parseo de la biblioteca de prompts y flujo /metrics completo).

### Cambiado
- El mapeo automático de columnas pasa de ~40 palabras clave fijas a un
  diccionario de datos versionado en el repo: agregar cobertura para un rubro
  nuevo es editar el CSV, no tocar código.

## [0.9.0] - 2026-07-09 - Fase 8: Panel de administración, soporte, gating comercial y adaptividad

### Agregado
- **Panel "Administrar cuentas"** (`/admin`, ítem del sidebar visible solo para la
  cuenta administradora): lista TODAS las cuentas de ADS Veris con semáforo
  (🔴 solicitudes pendientes / 🟢 al día), detalle por cuenta (datos visibles,
  registro, último acceso, archivos cargados — nunca contraseñas), **activación
  manual de planes** (selector Básico/Analista/Gold) y **otorgamiento de tokens**.
  Backend: `GET /admin/accounts`, `POST /admin/accounts/{id}/plan`,
  `GET /admin/support`, `POST /admin/support/{id}/attend`,
  `POST /admin/addon-requests/{id}/attend` — todos exigen `profiles.is_admin`.
- **Cuenta administradora**: migración `0010` marca `servicios@adsveris.com` como
  `is_admin`. El admin **pasa todas las puertas de plan** (capacidades y cupos
  ilimitados) sin depender del plan asignado.
- **Costura de pasarela de pago**: `set_user_plan()` es la única vía para cambiar
  planes (auditada en `admin_audit`); cuando exista el checkout (Webpay/Flow/
  MercadoPago), el webhook de pago llamará esa misma función. En el frontend,
  `startCheckout()` (lib/plans.ts) es el punto único a reemplazar; el botón de
  Planes pasó a "Contratar este plan" y hoy registra la solicitud.
- **Botón "¿Necesitas ayuda?" funcional**: modal de soporte en el sidebar
  (`POST /support/request`, tabla `support_requests` de la migración `0010`); la
  solicitud llega a la bandeja del administrador y pone a esa cuenta en rojo.
  Responde una persona, sin IA.
- **Retención de archivos en Storage** (`POST /storage/retention`, disparado tras
  cada subida): tope por plan (10 Básico / 25 Analista / 50 Gold), purga de lo no
  usado hace más de 60 días, y los **5 más recientes jamás se tocan**. Los datasets
  purgados conservan su historial con `storage_path` en null.
- **`/metrics` expone `dimensiones`**: qué columnas reales trae el dataset (fecha,
  monto, costo, cantidad, categoría, producto, canal, sucursal, cliente, vendedor).
- **Explorar datos adaptativo**: los análisis se adaptan al archivo — sin columna de
  canal/sucursal no aparece ese recuadro (ni en presets ni en "Agrupar por"); igual
  con categoría, producto y fechas.
- **Resumen adaptativo**: con archivo sin costos, en vez de tres tarjetas en "—"
  se muestran KPIs reales (Ticket Promedio, Transacciones, Tendencia Mensual) y una
  nota de cómo habilitar ganancia/margen. Las tarjetas de canal/categoría/productos
  solo aparecen si el archivo trae esas columnas.
- **Motor §5.14**: números con símbolo/código de moneda ("$ 1.200.000",
  "CLP 850.000", "US$1.500", "€200"), porcentajes ("12,5%") y **negativos contables
  "(1.500)"**; **filas de totales al final** ("Total", "Subtotal", "Suma") se omiten
  con aviso — ya no duplican los ingresos del dashboard.

### Cambiado
- **`PLAN_ENFORCEMENT` ENCENDIDO por defecto** (backend + frontend): descargar la
  base limpia (Excel/CSV) y la limpieza dirigida exigen Plan Analista; al intentar
  una función bloqueada aparece el aviso "Necesitas el Plan X" con botón directo
  **"Ir a comprar el plan"** (componente `PlanUpsell`). Sin Supabase configurado
  (desarrollo local) la puerta hace fail-open, igual que las cuotas.
- **El reporte PDF del negocio pasa a TODOS los planes** (`download_reports` →
  Básico): lo que se reserva para Analista es la descarga de la base LIMPIA.
- **Cupo de limpieza dirigida por plan**: de 2/mes a **10/mes (Analista)** y
  **25/mes (Gold)** (`AI_CLEANING_MONTHLY_LIMIT`, `AI_CLEANING_MONTHLY_LIMIT_GOLD`),
  siempre + tokens addon. La interpretación consume pocos tokens por intento; con 10
  el plan se siente útil sin riesgo de costo.
- **Limpieza de datos rediseñada, sin espacio muerto**: los pasos pasaron de columna
  lateral a **barra horizontal compacta**, el mapeo de columnas se extendió a lo
  ancho (2–5 columnas según pantalla) y la vista previa usa todo el ancho útil.
- **"Descargar base actualizada" con protagonismo propio**: tarjeta dedicada con
  botón primario (antes era un botón secundario pequeño), CSV al lado y "Continuar"
  en la misma fila.
- **Más color, sin estridencia**: tonos suaves (gradientes al 4–8%) en las tarjetas
  de Resumen (tinte del color de cada KPI), Limpieza, Estandarización y el panel
  admin; el blanco sigue mandando.

### Seguridad
- `admin_audit` (migración `0010`): todo cambio manual del administrador (plan,
  créditos, soporte atendido) queda registrado con quién, a quién y cuándo.
- Los endpoints `/admin/*` validan `is_admin` en el backend en cada llamada (la UI
  solo esconde el ítem del menú; la puerta real está en la API).

### Verificado
- **80 tests de la API en verde** (18 nuevos de Fase 8: admin 403/503, set-plan con
  auditoría, soporte, retención con keep-last intocable, dimensiones de /metrics,
  moneda/porcentaje/negativo contable, fila de totales) + build de producción OK.
- **E2E Playwright x2**: (1) pipeline completo con limpieza dirigida, descarga xlsx,
  modal de ayuda y Planes; (2) archivo mínimo sin canal/costos/categoría → Resumen
  sin tarjetas vacías, Explorar sin presets imposibles y fila "Total" excluida de
  los ingresos.

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
