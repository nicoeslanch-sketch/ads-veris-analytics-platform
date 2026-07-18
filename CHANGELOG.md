# Changelog — ADS Veris Plataforma de Análisis de Datos

Formato: [Keep a Changelog](https://keepachangelog.com/es/). Fases según [`SPEC.md`](./SPEC.md).

## [0.20.0] - 2026-07-17 - Fase 17: multihoja simple y análisis seguro

- El plan Básico confirma solo campos críticos dudosos, uno por uno, sin
  confianza, métodos ni vocabulario técnico; Analista y Gold conservan la vista avanzada.
- Permite elegir todas o algunas hojas y estandarizarlas/limpiarlas en orden,
  con progreso, error y reintento independientes.
- Resumen y Explorar comparten un alcance: una hoja, hojas compatibles apiladas
  con `hoja_origen`, o una relación many-to-one confirmada.
- Detecta claves simples y compuestas mediante cobertura, solapamiento,
  unicidad, cardinalidad y tipos; bloquea many-to-many y cambios de filas o totales.
- La descarga XLSX conserva todas las hojas originales y agrega Observaciones,
  Auditoría y Manifest. CSV multihoja se entrega como ZIP auditable.
- Corrige `TipoCliente`: ahora es `tipo_cliente`, nunca categoría de producto.
- La migración aditiva `0021_multi_sheet_analysis.sql` persiste selección,
  errores y alcance analítico; se entrega sin aplicar.

Diseño, umbrales y operación: [`docs/FASE_17_MULTIHOJA.md`](./docs/FASE_17_MULTIHOJA.md).

## [0.19.0] - 2026-07-17 - Fase 16: integridad auditable y restauración atómica

- Conserva literales reservados en columnas textuales y separa nulo físico,
  placeholder semántico contextual y texto literal durante carga, limpieza y exportación.
- Detecta moneda sobre todas las filas de montos y costos mediante una estructura
  tipada; una mezcla incompatible bloquea KPIs monetarios en API, IA y todas las vistas.
- Reserva la revisión al recibir el trabajo y persiste snapshots multihoja v3 mediante
  RPC atómica, con validación de SHA, reglas, mapeo, hoja y versión del motor.
- Expone calidad antes/después con una fórmula común y cobertura basada en valores válidos.
- Agrega auditoría por transformación; Excel incluye `Auditoria` y CSV se entrega como
  ZIP con datos, auditoría y manifiesto.
- Migra el E2E a `@playwright/test`, integra Chromium en CI y endurece el smoke RLS/Storage.
- Corrige la numeración duplicada de migraciones: contratación Básico pasa a `0019` y
  el estado de restauración v3 a `0020`.

La comprobación crítica punto por punto, los pasos manuales y riesgos residuales están
en [`docs/FASE_16_AUDITORIA.md`](./docs/FASE_16_AUDITORIA.md).

## [0.18.0] - 2026-07-17 - Fase 15: "todo en 10" — triage verificado del plan externo

Implementación CRÍTICA del plan de 8 ejes: cada afirmación se verificó contra
el código (todas las que tocaban código eran reales), lo operacional que no
vive en el repo se convirtió en runbook accionable (`docs/OPERACION.md`), y
lo desproporcionado quedó documentado con su razón (misma sección §6 del
runbook). Requiere ejecutar la migración **`0017`** y setear
**`APP_ENV=production`** en Render.

### Bugs P0 verificados y corregidos
- **`upgrade_basico` no existía para el backend**: la solicitud de contratar
  el Plan Básico se degradaba en silencio a "otro" (el admin la veía sin
  saber qué plan pedía el usuario) y el CHECK de Supabase la habría rechazado
  de enviarse tal cual. `REQUEST_TYPES`/`UPGRADE_REQUEST_TYPES` la reconocen
  y la migración `0017` alinea el constraint (con reparación opcional de
  solicitudes históricas degradadas).
- **Literales `nan`/`NaT`/`None` borrados**: el loader convertía a vacío el
  TEXTO literal escrito por el usuario (una categoría llamada "None" son
  datos, no un nulo). Ahora los nulos REALES se detectan ANTES de pasar a
  texto (máscara) y `keep_default_na=False` también en Excel — los vacíos
  reales siguen vacíos, los literales sobreviven.
- **KPI del admin contaba mal**: "Planes de pago activos" era
  `plan !== 'basico'` — contaba cuentas SIN plan como pagadas y excluía a
  los Básico. Ahora cuenta plan asignado real (basico/analista/gold); el
  estado de PAGO vendrá del modelo `subscriptions` junto con la pasarela.
- **Monedas mixtas ya no suman peras con manzanas**: flag explícito
  `moneda_mixta` en el backend y el Resumen BLOQUEA los indicadores
  monetarios con explicación y CTA (jamás una cifra sumada inválida).
- **Dos fuentes de RUT unificadas**: Configuración editaba `profiles.rut` en
  texto libre mientras la contratación usa `billing_identities` validada con
  módulo 11. El formulario ya no escribe RUT; muestra la identidad de
  facturación ENMASCARADA (read-only) y `profiles.rut` queda como legado.
- **Errores técnicos de Supabase en recuperación de contraseña**: el
  traductor de errores ahora es fail-closed (mensaje propio genérico para lo
  no mapeado, detalle solo en consola) y la recuperación lo usa.

### Exactitud y limpieza
- **Líderes brutos ANTES del recorte**: `lideres_productos` (por ventas
  brutas —con su participación—, netas, utilidad y mayor devolución) se
  calcula sobre TODOS los productos; un producto con brutas altas y
  devoluciones altas ya no desaparece del top-12 ordenado por netas.
  La concentración de clientes también usa la participación bruta.
- **Política de fusiones por ROL** (adoptada del informe, con matices): las
  ENTIDADES comerciales (cliente, producto, vendedor, categoría) JAMÁS se
  fusionan solas por typo/morfología/abreviación — pasan a SUGERENCIA
  visible para que el usuario confirme. Las abreviaciones chilenas de
  lugares (Stgo→Santiago) solo se aplican solas en columnas geográficas
  (rol sucursal o encabezado ciudad/comuna/región/dirección/zona); "Stgo"
  en una columna de productos podría ser un modelo.
- **Calidad MULTIDIMENSIONAL**: `calidad_dimensiones` con seis componentes
  (completitud, validez, consistencia, unicidad, integridad, cobertura
  analítica) junto al índice global — un archivo con conflictos de identidad
  ya no puede esconderse tras una nota única.

### Arquitectura y seguridad
- **Snapshots v2**: declaran `engine_version` (un snapshot de OTRO motor se
  invalida y se recalcula — resultados jamás mezclan versiones), procedencia
  auditable (`source_sha256`, `rules_hash`, `mapping_hash`, hoja) y
  `revision` monotónica: la escritura usa guardia por `generated_at` (una
  tarea de fondo antigua que termina tarde ya no pisa un snapshot más nuevo;
  con PostgREST antiguo degrada a escritura simple).
- **Arranque fail-closed en producción**: con `APP_ENV=production` la API se
  NIEGA a arrancar si falta Supabase, si `PLAN_ENFORCEMENT=false`, si
  `DEV_AUTH_BYPASS=true` o si CORS solo permite localhost — el error lista
  cada violación ("Startup failed: insecure production configuration").
- **`GET /version`**: identidad del despliegue (commit SHA de Render, versión
  del motor, migración esperada, entorno) — el smoke test post-deploy
  compara este SHA con el publicado.
- **Contrato único de planes — vía test, no duplicando endpoints** (matiz al
  informe): el riesgo real ya estaba cerrado con las capacidades del
  servidor en `/me/access`; lo que faltaba era detectar la divergencia de la
  matriz VISUAL de plans.ts. Un test de paridad lee plans.ts y compara
  contra capabilities.py — editar una sola de las dos matrices rompe el CI.
- **Límite de ráfaga de IA**: además del cupo mensual, máx. 12 llamadas/min
  por usuario (un loop accidental ya no quema tokens).
- **CI con job de seguridad**: `pip-audit` sobre requirements y `npm audit`
  (high+) bloquean el pipeline con dependencias vulnerables conocidas.

### Operación (lo que no es código, ahora es runbook)
- **`docs/OPERACION.md`**: checklist de release con smoke test por perfil,
  staging, protección de `main`, MFA y retiro de `ADMIN_EMAIL` tras
  bootstrap (mantenerla convierte un correo en credencial permanente —
  matiz: NO se eliminó el default por código para no dejar fuera al admin
  actual antes de confirmar `is_admin`), simulacro de restauración de
  backups, rotación de claves y observabilidad mínima.
- **`api/scripts/smoke_rls.py`**: prueba de AISLAMIENTO entre clientes
  contra un entorno real (A no restaura/procesa/factura nada de B; rutas
  admin cerradas) — para correr tras cada cambio de RLS.
- **E2E versionado**: `frontend/e2e/e2e_plataforma.mjs` + `npm run test:e2e`
  (antes vivía fuera del repo).

### Decisiones conscientes (rechazos/aplazamientos con razón — runbook §6)
- Modelo `subscriptions` → junto con la pasarela de pago (hoy la operación
  es manual y el par plan+identidad la cubre; crear estados de suscripción
  sin pagos reales fabrica complejidad sin verdad que representar).
- Ledger de transformaciones POR CELDA y export auditable completo → fase
  dedicada (multiplica memoria en archivos grandes; el resumen por regla,
  auditoría de mojibake, fusiones con ejemplos y avisos ya existen).
- Restauración multihoja completa → requiere rediseñar el tope de 512 KB
  del snapshot.
- KPIs por moneda / conversión con tasa declarada → siguiente iteración
  (hoy el bloqueo evita la cifra inválida, que era el P0).
- Staging/observabilidad/backups/branch protection/MFA → operacional, en
  el runbook con pasos concretos (no son archivos de este repo).

### Verificación
- **Backend 309 tests** (21 nuevos de Fase 15: paridad TS↔Python, snapshot
  v2 e invalidación por motor, fail-closed de producción, literales
  preservados en CSV y Excel, política de fusiones por rol, calidad
  multidimensional, moneda mixta, líder bruto que sobrevive al recorte,
  upgrade_basico, ráfaga de IA, /version) + Vitest + build + E2E.

## [0.17.6] - 2026-07-16 - Fixes de pruebas manuales: demo gratuita

10 bugs encontrados probando el flujo de prueba gratuita de 15 días, más una
mejora no bloqueante (análisis guardados).

### Exactitud y fuente única de verdad
- **Calidad del dato inconsistente**: el círculo de Limpieza redondeaba
  (`Math.round`) el mismo valor que el texto y el Historial mostraban sin
  redondear (99,7% → "100%" en el círculo). Ambos usan ahora `formatNumber`.
- **Cupo de limpieza dirigida IA mal asignado durante la prueba gratuita**:
  `cleaning_limit_for` trataba cualquier plan que no fuera literalmente
  `"gold"` como si tuviera la base de Analista (10) — Básico y `sin_plan`
  (prueba gratuita) mostraban "0/10" cuando esa función ni siquiera está
  incluida en su plan. Ahora deriva de la matriz única de capacidades
  (`PLAN_CAPABILITIES`); base 0 se comunica como "No incluida en tu plan
  actual" en vez de un contador engañoso.
- **Nombre de archivo con ID técnico de Storage como prefijo**: el path
  interno antepone `Date.now()_` para evitar colisiones
  (`1784231134931_base3_distribuidora_grande.xlsx`); se mostraba tal cual en
  Reportes, Estandarización e Historial. Un helper único (`_display_filename`)
  lo limpia en el backend, en la fuente.
- **Placeholders "período inicio — fin" sin fechas reales**: Reportes siempre
  pide el periodo COMPLETO del dataset (por diseño), así que `periodo.desde`/
  `hasta` son `null` el 100% de las veces. Ahora usa `fullRangePeriod` sobre
  `meses_disponibles` para mostrar el rango real, en la vista previa, el CSV
  y el PDF.

### Interfaz
- **Sin confirmación al contratar un plan**: el botón "Contratar este plan"
  ya tenía un estado de éxito, pero ninguno de error — una solicitud
  rechazada (ej. 409 por duplicado pendiente) volvía al botón normal sin
  ningún aviso visible cerca del punto de clic.
- **Textos de debug visibles en producción**: "requiere Supabase y la
  migración 0006/0008/0009" en Configuración y Planes, reemplazados por
  "Disponible próximamente."
- **Campana de notificaciones sin funcionalidad**: no había backend de
  notificaciones detrás; se oculta hasta que exista una fuente real (ya
  existe "Mis solicitudes" en el modal de ayuda como alternativa honesta).

### Explorar datos
- **Selector de periodo global desincronizado del "Rango" de Explorar**: eran
  dos estados independientes; cambiar el topbar no tocaba Explorar y
  viceversa. Ahora comparten el mismo `period`/`setPeriod` del contexto,
  igual que Resumen.
- **Primera letra recortada en las etiquetas del gráfico de barras**
  ("Aceite maravilla 900ml" → ".ceite..."): el `<text>` SVG del eje de
  categorías desbordaba el ancho asignado y Recharts lo recortaba desde el
  borde izquierdo. Se trunca el contenido con "…" antes de renderizar (tooltip
  nativo con el nombre completo).
- **"Hallazgos principales" no reactivo al cambiar de preset**: los 6
  hallazgos se calculaban solo desde `metrics`, ignorando si el usuario tenía
  seleccionado Tendencia/Productos/Categorías/Canales. Cada hallazgo ahora
  declara su categoría y los del preset activo se priorizan.

### Mejora no bloqueante
- **Vista de análisis guardados**: el botón "Guardar análisis" de Explorar
  funcionaba pero no había dónde consultarlo después. Nueva tarjeta en
  Historial, reutilizando las políticas RLS ya existentes de la migración
  0004 (sin migración nueva).

### Verificación
- 285 pytest + build de producción + typecheck, todos verdes.

## [0.17.5] - 2026-07-16 - Resumen sin espacios verticales artificiales

### Interfaz
- **Columnas independientes en escritorio**: las tarjetas del Resumen ya no
  comparten filas cuya altura dependía de la tarjeta más larga. Evolución y
  Categoría avanzan por la columna principal; Indicadores y Estado financiero,
  por la lateral.
- **Bloque inferior compacto**: Ventas por sucursal conserva su altura real y
  Top Productos/Proyección forman una segunda subcolumna, sin estirarse ni
  reservar huecos entre tarjetas.
- **Móvil sin cambios de orden**: la composición responsive conserva
  Evolución → Indicadores → Categoría → Estado financiero → bloque inferior.

### Verificación
- **21 Vitest + build de producción**, todos verdes.

## [0.17.4] - 2026-07-16 - Carga estable y acceso administrador coherente

### Acceso y carga de archivos
- **Se conserva el archivo elegido durante la revalidación**: abrir/cerrar el
  selector nativo provoca `focus` y una consulta nueva de acceso. El importador
  ahora espera esa respuesta autoritativa hasta 10 segundos, sin leer ni subir
  bytes antes de recibir permiso, en vez de descartar el archivo con
  "Estamos verificando tu acceso".
- **Estado explícito en los botones**: Estandarización y Google Sheets muestran
  "Verificando acceso..." y bloquean la acción solo mientras se resuelve.

### Administración
- **Rol separado del plan comercial**: `servicios@adsveris.com` conserva
  `plan=basico`, pero se presenta como "Administrador · acceso total" y no
  recibe ofertas de upgrade ni compra de tokens.
- **Cuotas administrativas realmente ilimitadas**: insights y limpieza
  dirigida respetan `is_admin` tanto al ejecutar como al mostrar contadores.
- **Migración `0018_designated_admin_access.sql`**: corrige la fila actual y
  agrega un trigger idempotente para mantener `is_admin=true` en la cuenta
  designada, aunque haya sido creada después de la migración 0010.

### Verificación
- **279 pytest + 21 Vitest + build de producción**, todos verdes.

## [0.17.3] - 2026-07-16 - Recuperación de contraseña completa

### Autenticación
- **Panel público de nueva contraseña**: el enlace enviado por Supabase abre
  `/restablecer-contrasena`, valida dos campos coincidentes y aplica la misma
  política del registro (mínimo 8 caracteres, letras y números).
- **Cierre seguro del flujo**: después de actualizar la contraseña se cierra la
  sesión de recuperación y se redirige al inicio de sesión con confirmación.
- **Enlaces antiguos compatibles**: los correos ya emitidos con
  `type=recovery` hacia la raíz se redirigen al panel nuevo; los enlaces
  inválidos o vencidos muestran una salida clara para solicitar otro.
- **Supabase Auth alineado**: Site URL de producción, redirects exactos para
  producción/desarrollo y política remota `8 + letters_digits`.

### Verificación
- **21 Vitest + build de producción**, todos verdes.

## [0.17.2] - 2026-07-16 - Fase 14c: cierre comercial y consistencia analítica

Revisión crítica del informe posterior a 14b. Se confirmaron tres defectos
funcionales y cuatro endurecimientos relevantes; se evitó reordenar globalmente
las tablas por ventas brutas porque habría desalineado barras y montos netos.

### Seguridad y operación comercial
- **Upgrade con identidad obligatoria en backend**: `POST /addons/request`
  devuelve 422 para `upgrade_analista` y `upgrade_gold` sin
  `billing_identity_id`; la propiedad de la identidad sigue verificándose.
- **Correo confirmado autoritativo**: el trial consulta Supabase Auth Admin
  (`email_confirmed_at`/`confirmed_at`) y deja de confiar en `user_metadata`,
  que el usuario puede editar. Un fallo de Auth cierra con 503.
- **Rate limits independientes**: trial por usuario, trial por RUT y registro
  de identidad de facturación ya no consumen el mismo bucket.
- **AccessProvider fail-closed durante refrescos**: `can()` solo habilita una
  capacidad con estado `resolved`; una capacidad stale puede seguir dibujada
  en contexto, pero no habilita acciones mientras se revalida.

### Exactitud y administración
- **Concentración bruta correcta sin romper rankings netos**: productos,
  canales y clientes usados en afirmaciones de concentración seleccionan el
  máximo `participacion_bruta_pct`. Las tablas generales conservan el orden
  por ingreso neto, evitando barras no monotónicas después de devoluciones.
- **Mes parcial sin fallback**: Resumen usa siempre `soloMesesCompletos`;
  con un único mes completo muestra el mejor mes, pero no inventa crecimiento
  usando el parcial. Alertas consume el mismo helper y corrige su copy.
- **Bandeja administrativa útil y privada**: los upgrades muestran tipo, ID y
  RUT enmascarado de la identidad; `rut_normalized` nunca sale de la API.
- **Migración `0017_billing_identity_retention.sql`**: las referencias de
  solicitudes y trials usan `ON DELETE SET NULL`, permitiendo atender una
  eliminación de la identidad reutilizable sin borrar el historial ni
  habilitar otra prueba gratuita.

### Verificación
- **276 pytest + 15 Vitest + build de producción**, todos verdes.
- Pruebas nuevas: upgrade sin identidad, señal autoritativa de Auth, buckets
  separados, concentración bruta con devoluciones, identidad enmascarada en
  administración y contrato de la migración `0017`.

## [0.17.1] - 2026-07-16 - Fase 14b: estabilización — triage verificado del informe de Fase 14

Los CUATRO P0 del informe externo se verificaron como reales en el código y
quedan cerrados; se suman correcciones propias que ningún informe mencionó.
La migración `0016` cambió: si ya la ejecutaste, **vuelve a ejecutarla**
(es re-ejecutable: `create or replace` + `if not exists`).

### P0 del informe — verificados y corregidos
- **Elegibilidad del trial** (P0.1): un usuario Básico/Analista/Gold o un
  administrador podía activar la prueba y RESERVAR el RUT de otra empresa
  (impidiendo que su titular legítimo probara la plataforma). Ahora la API
  pre-verifica (403 "la prueba es para cuentas nuevas sin plan") y la RPC
  re-verifica `profiles.plan`/`is_admin` como AUTORIDAD FINAL
  (`USER_HAS_ACTIVE_PLAN`). Además: correo confirmado exigido cuando el JWT
  declara explícitamente `email_verified: false` (lenient: proyectos sin
  confirmación no se rompen).
- **Minimización de datos en la activación** (P0.2): si el trial fallaba por
  RUT ya usado, la identidad recién insertada QUEDABA guardada (la función
  retornaba normal y la transacción confirmaba). La RPC ahora registra si la
  identidad se creó en esa llamada y la elimina al fallar el trial — una
  identidad previa (de una contratación) se conserva intacta.
- **RUT al contratar** (P0.3): "Contratar este plan" ahora exige la identidad
  de facturación — si no existe, se abre el MISMO formulario compartido
  (contexto contratación), se registra vía `POST /me/billing-identity` y la
  solicitud viaja con `billing_identity_id` (columna nueva en
  `addon_requests`, con verificación de propiedad en el backend) — jamás el
  RUT en texto libre. `GET /me/access` expone la identidad enmascarada y la
  tarjeta del plan la muestra ("Facturación: RUT 12.***.***-5").
- **La demo jamás escribe** (P0.4): "Guardar análisis" en Explorar guardaba
  hallazgos FICTICIOS en `analyses`/`activity_log` — incluso asociados a un
  dataset real del usuario. El botón no existe en demo y el handler tiene
  guard (verificado por E2E: sin botón en demo, presente con datos reales).

### Exactitud (altas del informe — verificadas)
- **Explorar y meses parciales**: los hallazgos ("subieron/cayeron", mejor y
  peor mes) usaban la serie completa — era el único módulo que seguía
  comparando el mes parcial contra uno completo. Ahora consume el helper
  único `soloMesesCompletos` (lib/partial.ts) igual que Alertas y Resumen.
- **Utilidad desconocida ya no vuelve a ser $0**: la tendencia mensual de
  Explorar hacía `utilidad ?? 0` (gráfico, variaciones y participaciones
  falsas). Ahora se mantiene `null` hasta el final: hueco en la línea
  (`connectNulls=false`), "—" en la tabla, sin variación ni participación, y
  nota "no es $0, es desconocida".
- **Participación bruta que SÍ suma 100%**: cada grupo expone
  `ventas_brutas`, `devoluciones`, `ventas_netas` y `participacion_bruta_pct`
  (invariante: suma ≈100%, con test). Toda afirmación de CONCENTRACIÓN
  (hallazgos, alertas de producto/canal, concentración de clientes, tablas
  del Resumen "% Ventas brutas") usa la bruta; el % neto se conserva para
  mostrar el efecto de las devoluciones.
- **Copy de parcialidad sin causa inventada**: "El último registro disponible
  corresponde al día N de D…" — declara el hecho y la regla conservadora,
  jamás afirma que "faltan datos" (el archivo no permite saber la causa).

### Arquitectura y accesibilidad
- **AccessProvider sin fuga entre cuentas** (hallazgo propio sobre la
  observación del informe): al cambiar de usuario en el mismo navegador, el
  acceso anterior se limpia AL INSTANTE; el "stale-while-revalidate" del
  refresco por foco aplica SOLO al mismo usuario (sin parpadeo de candados y
  sin capacidades ajenas).
- **Rate limiting también por RUT**: alternar cuentas ya no permite sondear
  el mismo RUT sin límite (ventana por usuario Y por RUT normalizado — el
  RUT jamás se loguea). El límite compartido multi-instancia queda documentado
  como pendiente para campañas públicas.
- **Modales**: TrialModal resetea su estado al reabrirse (antes conservaba
  error/éxito), cierra con Escape y enfoca el diálogo; PlanRequiredModal y el
  modal de facturación también cierran con Escape.
- **Copys de la demo**: "así se ve la plataforma con datos ficticios
  realistas de un negocio" (antes decía "datos reales", contradiciendo la
  etiqueta).

### Verificación (respuesta al 3/10 del informe en pruebas)
- **Backend 269 tests** (17 nuevos): gates probados por HTTP REAL con
  TestClient — 403 verificado en /ai/*, /metrics y /restore/latest con
  aserciones de que Anthropic NO se llama, el motor NO procesa y restore NO
  corre; el trial vigente SÍ pasa /metrics (200 con KPIs) y la IA sigue 403;
  elegibilidad de activación (plan pagado/admin/correo sin confirmar);
  identidad ajena 422; invariante de participación bruta; copy sin causa.
- **Frontend: Vitest estrenado** (`npm run test`, 12 pruebas): paridad del
  RUT con Python (mismos casos que pytest — si una implementación cambia
  sola, una suite falla) y la regla de meses parciales.
- **E2E 21/21**: se agregó "la demo NO ofrece guardar análisis / con datos
  reales SÍ" y los copys nuevos de parcialidad.
- Pendiente honesto: la RPC de la 0016 se verifica estructuralmente en tests
  (elegibilidad + reversa de identidad presentes) — la ejecución real contra
  PostgreSQL queda para el smoke test operativo en Supabase.

## [0.17.0] - 2026-07-16 - Fase 14: cierres P0 comerciales, prueba gratuita con RUT, demo ficticia y acceso unificado

Implementa el **análisis de calidad definitivo** consolidado en el debate
técnico (réplicas incluidas). Requiere ejecutar la migración **`0016`** en
Supabase y configurar la política de contraseñas en el Dashboard (ver README).

### Cierres P0 — los cuatro bypasses comerciales quedan cerrados
- **`/ai/summary`, `/ai/chat`, `/ai/recommendation`** ahora exigen la
  capacidad `ask_data_ai`. Era el bypass MÁS CARO: el cliente envía las
  métricas como JSON, así que una cuenta sin plan podía consumir tokens de
  Anthropic sin haber procesado jamás un archivo.
- **`/metrics`** exige `view_dashboard` (reprocesaba el archivo completo sin
  puerta) y **`/restore/latest`** también (su fallback reconstruye el
  pipeline). El frontend trata el 403 de restauración como "nada que
  restaurar", sin romper la navegación.
- **Cuota de IA**: `sin_plan` tiene límite 0 EXPLÍCITO — antes era un
  `KeyError` → 500 en `/ai/usage` para toda cuenta nueva. Sin plan la IA
  responde 403 con CTA ("disponible desde el Plan Básico"), no un 429.
- **Conector de Sheets**: la puerta comercial va ANTES de
  `POST /connectors/sheets` — antes la llamada salía primero y el usuario
  bloqueado veía un 403 crudo en vez del modal. Además, todas las puertas
  de capacidad corren en threadpool (no bloquean el event loop).

### Contexto de acceso ÚNICO (servidor como fuente de verdad)
- Nuevo **`GET /me/access`**: plan pagado, admin, estado de la prueba
  gratuita y **capacidades efectivas calculadas en el servidor**. El
  frontend (nuevo `AccessProvider`, tres estados loading/resolved/error) ya
  no reconstruye capacidades desde el plan ni arranca "optimista" como
  Básico mientras carga — la carrera del `usePlan` quedó cerrada: ninguna
  puerta se abre sin el acceso resuelto.
- `usePlan`/`useCapability` son adaptadores compatibles sobre el contexto.

### Prueba gratuita de 15 días (Básico sin IA) con RUT
- **Migración `0016`**: `billing_identities` (RUT empresa o responsable,
  reutilizable para contratación) y `account_trials` con **una prueba por
  usuario (unique absoluto, para siempre)** y **una prueba VIGENTE por RUT
  (índice único PARCIAL sobre `revoked_at is null`)** — revocar una prueba
  apropiada libera el RUT para su titular legítimo, pero quien abusó no
  reactiva jamás.
- **Activación 100% atómica en Postgres**: RPC `activate_account_trial`
  (SECURITY DEFINER, search_path fijo, ejecutable SOLO por la service_role
  — el rate limiting de la API es insoslayable y ningún cliente pasa un
  user_id ajeno). Fechas del SERVIDOR (`now() + 15 días`); la vigencia se
  evalúa contra `now()`: **sin cron, sin campo "activo" mantenido a mano**.
- **RUT**: normalización idéntica en frontend, backend y SQL (puntos/
  espacios/guiones fuera, K mayúscula, canónico `CUERPO-DV`), módulo 11 en
  las tres capas, SIN piso arbitrario de cuerpo (hay RUN legítimos antiguos
  bajo 1.000.000). Jamás en URLs/logs/JWT; se muestra enmascarado
  (`12.***.***-5`). El formulario declara la finalidad según el contexto
  (prueba vs contratación) y cómo pedir corrección.
- **Privacidad de errores**: los del PROPIO usuario son específicos ("Tu
  cuenta ya utilizó la prueba"); los que involucran a terceros colapsan a
  un mensaje genérico — el RUT no es un oráculo para enumerar clientes.
  Rate limiting de activación (5 intentos / 10 min).
- **`TRIAL_CAPABILITIES`** = estandarizar, limpiar, dashboard y reportes
  (incluye Sheets/Explorar/Alertas/Historial). Excluidos: asistente IA,
  limpieza dirigida, descarga de base limpia, SQL y comunidad — la IA es la
  diferencia comercial entre probar y contratar. `profiles.plan` NO se toca.
- Al expirar: los archivos se conservan según retención, el procesamiento
  nuevo se bloquea (mensaje propio "Tu prueba gratuita terminó") y Planes/
  Configuración/Historial siguen navegables.
- **RLS restrictiva**: nueva función `can_process_data()` (STABLE,
  `auth.uid()` interno — parametrizarla sería un oráculo) y políticas
  **`AS RESTRICTIVE`** en `datasets` y `storage.objects` (solo bucket
  datasets): las políticas permisivas de propiedad se combinan con OR, por
  lo que agregar otra permisiva no habría cerrado nada.

### Demo ficticia regenerable ("Comercial Andes SpA")
- CSV ficticio versionado (`api/demo/demo_empresa_ficticia.csv`) con
  devoluciones, costos incompletos, duplicados, textos inconsistentes y un
  mes parcial A PROPÓSITO — la demo muestra la plataforma explicando datos
  imperfectos, que es el caso real de una PyME.
- Los snapshots del frontend **nacen del motor real**
  (`api/scripts/generate_demo.py` → `frontend/src/demo/data/*.json`) y un
  test de contrato los regenera y compara: si el esquema cambia, falla
  ruidosamente — la demo no puede desincronizarse en silencio.
- **`DemoProvider` independiente**: la demo jamás escribe en el
  DatasetContext, no llama al backend, no toca Storage ni historial; salir
  restaura el estado vacío exacto. Etiqueta persistente "Datos ficticios de
  ejemplo" en todas las páginas.
- Botones **"Ver demo ficticia"** y **"Probar demo gratuita (15 días)"** en
  los estados vacíos de Resumen, Explorar y Limpieza (el de prueba solo
  para cuentas sin plan que no la usaron). En la demo, la IA queda
  desactivada con mensaje claro (cero llamadas).

### Interceptación de carga (las TRES puertas, antes de cualquier byte)
- **Selector de archivos**: el modal comercial aparece ANTES de abrir el
  picker (también en "Estandarizar nuevo documento").
- **Drag & drop**: `preventDefault` + puerta antes de leer el archivo.
- **Sheets**: puerta antes del POST. Regla general: ningún byte sale del
  navegador y ninguna llamada de procesamiento comienza sin el contexto de
  acceso resuelto y aprobado; `useFileImport` re-verifica por defensa en
  profundidad. El modal ofrece activar la prueba, ir a Planes o ver la demo
  (y distingue "prueba expirada").

### Parcialidad POR MES en la evolución (Alertas/proyección/IA/gráfico)
- Cada mes de `evolucion_mensual` declara `parcial`, `cobertura_hasta_dia`
  y `dias_del_mes` (el flag global de la Fase 13 solo existía al filtrar).
- **La proyección excluye el mes parcial** de la tasa y la base (un mes a
  medio llenar simulaba una caída) y sus meses proyectados empiezan DESPUÉS
  del final real — sin superposición con meses que tienen datos.
- **Alertas** ya no compara un mes parcial contra uno completo (usa los dos
  últimos completos y lo dice). "Mejor mes" y "Crecimiento del periodo"
  excluyen o identifican el parcial. **La IA recibe la marca** ("mes
  incompleto: datos hasta el día N") y el gráfico lo señala con asterisco y
  nota al pie.

### Registro reforzado (accesible)
- Campo **"Confirmar contraseña"** con tick verde SOLO cuando coincide Y
  cumple la política; aviso `aria-live` ("Las contraseñas [no] coinciden");
  envío bloqueado si difieren. **Ojos** para mostrar/ocultar en ambos
  campos (aria-label, operables por teclado, sin borrar el valor ni robar
  el foco). `autocomplete="new-password"`; pegar SIGUE permitido (bloquear
  el pegado castiga a quien usa gestor de contraseñas). Recordatorio: la
  política REAL se configura en Supabase → Authentication → Providers →
  Email (mínimo 8, letras y números) — la validación del formulario es UX.

### Precisión numérica: promesa exacta de float64
- `format_number` usa `repr()` (el texto MÁS CORTO que reconstruye el mismo
  float64) con guarda de finitud — el `.9f` de la Fase 13 aún cortaba colas
  legítimas. Aplica a valores parseados (estandarización); los agregados de
  métricas mantienen sus `round()` (la aritmética binaria produce
  artefactos que `repr` mostraría).

### Verificación
- **252 tests** (28 nuevos: RUT/módulo 11/idempotencia/enmascarado, trial
  vigente/expirado/revocado, capacidades efectivas, gates estructurales de
  /ai + /metrics + /restore, cuota sin_plan, rate limiting, privacidad de
  errores, parcialidad por mes, proyección sin superposición, repr(), y el
  contrato de regeneración de la demo) + build + **E2E 19/19** (demo
  completa entrar/navegar/salir, pipeline real intacto con las puertas
  nuevas, mes parcial marcado, registro reforzado con aria-live y ojos).

## [0.16.0] - 2026-07-15 - Fase 13: cuentas sin plan, contraseña reforzada y triage verificado del 3er informe

### Modelo comercial (pedido del dueño)
- **Las cuentas NUEVAS nacen sin plan** (migración `0015` — ejecutarla en
  Supabase): pueden navegar toda la plataforma, pero al intentar subir o
  importar un archivo aparece el panel "Necesitas un plan activo" con CTA
  directo a Planes. El backend refuerza lo mismo (403 en /standardize, /clean
  y el conector de Sheets para plan `sin_plan`). **Las cuentas existentes no
  se tocan: conservan su plan actual y funcionan exactamente igual.**
- **Contraseña reforzada al registrarse**: mínimo 8 caracteres con letras y
  números (validación con mensaje claro en el formulario).

### Hallazgo propio (no estaba en ningún informe): fechas ISO volteadas
- pandas con `dayfirst=True` interpretaba "2026-05-01" (año-mes-día, el
  formato con que Excel serializa fechas) como año-DÍA-mes: **el 1 de mayo se
  convertía en 5 de enero**. En la base real de regresión, la evolución
  mensual mostraba 12 meses fabricados donde los datos reales tienen SOLO
  abril y mayo. Corregido en `parse_date` (año-primero = ISO siempre) y las
  columnas datetime de Excel ahora se clasifican y estandarizan como fecha.

### P0 del informe externo, verificados y corregidos
- **Porcentajes con devoluciones** (§P0.3): la participación por producto/
  cliente/categoría/canal se calcula sobre ventas BRUTAS positivas — dividir
  por el neto mostraba "1.000%" con una devolución grande.
- **Mes incompleto** (§P0.4): si el mes seleccionado tiene datos solo hasta
  el día N, la variación compara los primeros N días del mes anterior (con
  aviso y flag `periodo.mes_parcial`) — antes comparaba 15 días contra 30 y
  mostraba caídas falsas. Lo decide el backend con los DATOS, no el reloj.
- **Monedas** (§P0.5): UF, ARS, PEN, COP, MXN y GBP ahora se detectan (el
  estandarizador ya quitaba sus tokens y quedaban como CLP silencioso).
- **Precisión numérica** (§P0.6): se eliminó el truncado a 2 decimales
  (0,0049 se convertía en 0,00) — la precisión se conserva; redondear es de
  la capa de presentación.
- **Horas conservadas** (§P0.7): "15/07/2026 08:15" mantiene su hora al
  estandarizar (la medianoche de Excel "00:00:00" no se conserva).
- **Calidad con la MISMA base antes/después** (§P0.1): los nulos preservados
  vuelven a contar en la calidad post-limpieza — una base con 10.000 celdas
  vacías ya no puede "subir a 100%" sin que se corrigiera nada.
- **Utilidad mensual desconocida ≠ $0**: un mes sin filas pareadas entrega
  utilidad null (antes la suma de NaN daba 0).
- **Conteo real de fusiones fuzzy**: el total ya no es la cantidad de
  ejemplos capados a 5.
- **"Total Energies" con dos columnas** ya no se elimina: la etiqueta de
  fila-total exige coincidencia EXACTA ("Total", "Subtotal"…).
- **CSV con comas entrecomilladas**: el detector de separador ignora lo
  citado ('ACME,"Servicio, instalación",100').
- **Copys coherentes**: "Registros" también en la rama sin costos; "sin
  columna de costos" ≠ "con costos pero sin ventas pareadas" (se distinguen);
  concentración de clientes dice "ventas identificadas" también en Explorar;
  cerrar sesión ya no impide restaurar el último trabajo al reingresar.
- **StrictMode (2º hallazgo propio)**: el camino que reutiliza métricas del
  contexto en Explorar quedaba con la clave pegada tras el doble montaje y
  los presets no se adaptaban al archivo — corregido con liberación de clave.

### Rechazado o postergado del informe (con razón)
- Retirar el porcentaje único de calidad (se corrigió su base; el rediseño
  multidimensional sigue en backlog), eliminar toggles de reglas (rotulados
  honestos por ahora; decisión de producto), bloquear KPIs con monedas
  mixtas (advertencia prominente; decisión de producto), fuzzy como
  sugerencia, versionado/invalidación de snapshots y restauración multihoja
  completa, auditoría CSV en ZIP, severidades estructuradas, Vitest,
  literales "nan"/"None" (el reemplazo del loader cubre NaN reales de
  pandas; distinguirlos exige refactor de carga).

### Verificación
- 224 pruebas backend (16 nuevas), build de producción y 2 suites E2E.

## [0.15.2] - 2026-07-15 - Ajustes móviles sin cambios en escritorio

- Estandarización mantiene las acciones del dataset activo dentro del recuadro
  y las apila únicamente en pantallas pequeñas.
- Historial usa fichas móviles de una columna en vez de una tabla con
  desplazamiento horizontal; la tabla original se conserva desde `lg` hacia
  arriba, igual que la navegación de escritorio.
- Reportes permite partir nombres de archivo largos únicamente en móvil para
  que nunca desborden el recuadro de contenido.

## [0.15.1] - 2026-07-15 - Restauracion persistente de datasets

- La reapertura del ultimo trabajo usa `POST /restore/latest`: una sola llamada
  devuelve estandarizacion, limpieza y metricas desde un snapshot versionado.
- Si el snapshot falta o queda obsoleto, el backend reconstruye el pipeline con
  pandas una vez y guarda el resultado; la exactitud del motor no cambia.
- Los snapshots solo pueden ser escritos por el backend con `service_role` y
  tienen un limite de tamano. El navegador conserva acceso solo a las columnas
  operativas de `datasets` mediante la migracion `0014_restore_snapshots.sql`.
- Resumen, Explorar, Alertas, Reportes e IA reutilizan las metricas restauradas
  en vez de iniciar otro procesamiento al montar la pagina.
- La retencion de Storage sale de la ruta critica y corre despues de restaurar.
- Verificacion: build de produccion y 208 pruebas backend, incluidas las de
  snapshot, fallback, propiedad y autenticacion.

## [0.15.0] - 2026-07-15 - Fase 12b: triage verificado del informe de calidad externo

Cada afirmación del informe se verificó contra el código antes de aceptarla;
lo confirmado se corrigió y lo especulativo o de riesgo quedó registrado como
pendiente. 202 pruebas backend (15 nuevas), build y E2E completos.

### P0 corregidos (confirmados en el código)
- **Los valores no interpretables se CONSERVAN**: la limpieza reemplazaba por
  vacío cualquier fecha o número que no pudiera interpretar ("31/02/2026",
  "$ 15.O00", "Pendiente confirmar") — destruía el original y la descarga ya
  no permitía reconstruirlo. Ahora se conservan, se marcan en la descarga
  ("Fecha/Número no interpretable: se conservó el valor original") y siguen
  penalizando la calidad post-limpieza: **la calidad ya no puede "mejorar"
  borrando la evidencia**.
- **"1,234" por evidencia de columna**: la coma única con 3 decimales es
  ambigua (decimal es-CL vs miles US). Se decide por evidencia de la MISMA
  columna ("12,5" o "1.234,56" → decimal; "1,234.56" o "1,234,567" → miles);
  sin evidencia se mantiene decimal (es-CL) **con aviso explícito** — un error
  aquí altera ingresos por un factor de mil.
- **Margen mensual pareado**: el sparkline de margen calculaba utilidad/
  ingresos del mes (ventas sin costo en el denominador) — reintroducía el bug
  corregido en el KPI global. El backend ahora entrega `margen_pareado_pct` y
  `cobertura_costos_pct` por mes y el frontend no deriva el margen.
- **StrictMode dejaba páginas colgadas** (hallado por E2E, no estaba en el
  informe): el doble montaje de React abortaba la petición inicial y la clave
  "ya pedida" impedía reintentar — Limpieza quedaba en "Analizando…" con el
  botón deshabilitado para siempre. Corregido en Limpieza, Resumen, Explorar,
  useSessionMetrics y AiPanel: al abortar se libera la clave.

### Exactitud del dashboard
- "Transacciones" → **"Registros"** (cuenta filas del archivo; sin clave de
  transacción declarada no se puede afirmar más) + `registros_con_monto` y el
  ticket promedio muestra su base real cuando difiere.
- **Devoluciones visibles**: los montos negativos se reportan como KPI
  (`devoluciones`) con advertencia "los ingresos son NETOS".
- **"Resultado del Periodo" eliminado**: era exactamente la misma Utilidad
  Bruta repetida — la 4ª tarjeta ahora muestra **Cobertura de Costos** con su
  propia evolución mensual.
- **Concentración de clientes honesta**: % sobre ventas identificadas +
  `cobertura_identificacion_pct` (si la mitad de las ventas no tiene cliente,
  el hint lo dice).
- **Cobertura por grupo**: categorías/canales/productos exponen `filas`,
  `filas_pareadas` y `cobertura_costos_pct`; Explorar exige cobertura ≥30% y
  ≥3 filas pareadas antes de recomendar "tu categoría más rentable", y la
  utilidad desconocida ya no se grafica como $0.
- `top_productos` hasta 12 (Resumen muestra 5; Explorar tiene qué explorar).
- Extrapolación etiquetada como tal ("si se mantiene el crecimiento promedio
  observado", meses usados, sin estacionalidad), "mes en curso: datos
  parciales" en el subtítulo, gráfico de evolución rotulado "contexto
  histórico completo", salud financiera "referencia general; depende del rubro".

### Motor y carga
- Columna con nombre "fecha" ya no se clasifica fecha con UNA celda con forma
  de fecha: la pista de nombre exige ≥30% real.
- Columnas vacías: **detectar sí, eliminar NO por defecto** (misma filosofía
  conservadora que los duplicados; el toggle sigue disponible).
- "Total Energies" al final del archivo ya no se elimina como fila de totales:
  la fila debe ser resumen real (resto de celdas numéricas o casi vacía).
- Límites de superficie: `MAX_COLUMNS` 300 y `MAX_TOTAL_CELLS` 4M con mensaje
  accionable (antes 200.000 filas × 500 columnas se "aceptaba" y caía).
- Los avisos de la estandarización (comas ambiguas, fechas mixtas, mojibake)
  ahora también llegan en la respuesta de limpieza.
- Alertas "revisadas" son por dataset: cargar otro archivo ya no hereda las
  revisiones del anterior (misma id de alerta).
- Copy honesto en reglas de Limpieza: la estandarización de formatos ocurre
  siempre; los toggles controlan las correcciones adicionales.

### Rechazado o postergado del informe (con razón)
- Bloquear KPIs con monedas mixtas (decisión de producto — hoy advertencia
  prominente), rediseño multidimensional del puntaje de calidad (el P0.1 ya
  eliminó su trampa principal), fuzzy de clientes/productos como sugerencia
  (cambio de producto mayor), auditoría CSV en ZIP con observaciones.csv,
  severidades estructuradas de advertencias, streaming del export Excel,
  semáforo de concurrencia, score combinado de mapeo, pruebas frontend con
  Vitest y literales "nan"/"None" como texto legítimo (caso borde). Quedan en
  PHASE_STATUS como backlog priorizado.

## [0.14.0] - 2026-07-15 - Exactitud auditada e indicadores PyME

### Exactitud y transparencia
- El margen por categoría, canal y producto usa únicamente filas con ingreso y
  costo pareados, igual que el KPI global. Si un grupo no tiene costos
  comparables, no se inventa un margen cero.
- La evolución mensual conserva costos de filas fechadas aunque el monto sea
  ilegible, y advierte cuando ventas sin fecha suman al total pero no pueden
  aparecer en el gráfico o en filtros mensuales.
- `dimensiones.monto` exige al menos un monto legible; una columna de puro texto
  vuelve a mostrar la guía de mapeo en lugar de un dashboard engañoso en $0.
- Los Excel con encabezados repetidos conservan todas las columnas y renombran
  las repeticiones con sufijos compatibles con pandas (`Total.1`, `Total.2`).

### Nuevos indicadores
- Resumen incorpora mejor día de venta y clientes únicos; Explorar señala
  concentración de clientes y el día de mayor venta cuando hay evidencia.
- `/metrics` expone ventas por día de la semana, concentración/top de clientes,
  y utilidad/margen pareados para categorías, canales y productos.
- Placeholders como `Sin Nombre` o `cliente desconocido` quedan fuera del conteo
  de clientes y de la concentración comercial.

### Verificación
- Se añadieron 13 pruebas de verdad calculada a mano para totales, cobertura,
  márgenes parciales, evolución, fechas ausentes, dimensiones, encabezados
  repetidos, clientes, días de venta y comparación mensual.

## [0.13.0] - 2026-07-13 - Fase 12: motor no destructivo e identidad de datos

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

### Bloque 2 — conteos honestos y controles monetarios
- El contador textual compara el valor final con el original: una celda que
  atraviesa varias etapas se cuenta una sola vez. El reporte separa espacios,
  variantes y celdas textuales únicas modificadas.
- Limpieza dejó de sumar filas, celdas, columnas y observaciones en un supuesto
  "total de problemas". La UI muestra cada categoría con su unidad y advierte
  que pueden superponerse.
- Montos cero, montos negativos y posibles atípicos IQR se reportan por separado.
  Ninguno modifica datos. El detalle IQR por columna incluye cuartiles, rango,
  límites y conteos bajo/sobre esos límites.

### Bloque 3 — semántica y codificación segura
- Los placeholders de cliente (`Sin Nombre`, `cliente desconocido`, etc.) se
  conservan literalmente, no se fusionan con nombres reales y se reportan como
  nulos semánticos separados de los vacíos físicos.
- El motor señala patrones estructurales mediante categorías simples y umbrales
  configurables; nunca imputa ni borra esos valores.
- El mojibake se repara solo con conversiones latin-1/cp1252 strict que reduzcan
  evidencia sospechosa. Cada propuesta conserva original, método, confianza y
  estado aplicado; los casos ambiguos quedan intactos.

### Bloque 4 — identidad y fórmulas Excel
- El motor cruza pares semánticos nombre↔ID de producto y cliente, y reporta
  tanto nombres asociados a varios identificadores como identificadores asociados
  a varios nombres. Conserva ejemplos y filas físicas de origen, sin corregir ni
  eliminar datos automáticamente.
- Los archivos `.xlsx` se inspeccionan con `openpyxl` en modo fórmula. El reporte
  excluye filas de título, vacías y totales, separa fórmulas volátiles y destaca
  fórmulas dentro de columnas identificadoras para revisión.
- La ausencia de fórmulas o un fallo tolerable de inspección no bloquea el
  pipeline; la auditoría se entrega como diagnóstico aditivo.

### Bloque 5 — procesamiento multihoja explícito
- Estandarización presenta las hojas como pestañas con estado procesada/sin
  procesar y conserva por hoja su estandarización, limpieza, mapeo y decisión
  sobre duplicados durante la sesión.
- La descarga XLSX recibe un manifiesto explícito que debe enumerar todas las
  hojas reales. El caché solo acelera; nunca decide qué hojas entran. Cada hoja
  marcada se exporta limpia y las no procesadas quedan registradas en una hoja
  consolidada `Observaciones`.
- Hojas con el mismo conjunto de encabezados normalizados se pueden combinar
  únicamente tras confirmación, en `Datos_combinados`, con `hoja_origen`. No se
  realizan JOIN automáticos entre estructuras distintas.
- Resumen y Explorar muestran un selector de hoja activa y limpian las métricas
  anteriores antes de recalcular, evitando mezclar el nombre de una hoja con
  resultados todavía pertenecientes a otra.

### Bloque 6A — eliminación recuperable desde Historial
- Historial incorpora una acción accesible de eliminación con diálogo modal,
  foco en Cancelar, trampa de foco, confirmación irreversible y aviso especial
  cuando se elimina el dataset activo.
- `DELETE /datasets/{id}` orquesta una saga durable e idempotente: persiste el
  trabajo, valida propiedad, elimina Storage y recién entonces finaliza la fase
  PostgreSQL. Un fallo guarda etapa y error para retomar sin repetir fases ya
  confirmadas.
- La migración `0013_dataset_deletion_saga.sql` crea los trabajos de eliminación
  sin FK al dataset y una RPC transaccional que conserva el log, ejecuta las
  cascadas y marca `completed` de forma atómica.

### Bloque 6B — mapeo progresivo y confianza semántica
- Los diez selectores permanentes se reemplazaron por chips compactos y un panel
  Ajustar. El panel muestra primero roles asignados y luego solo roles críticos
  sin asignar que tengan candidatos semánticos de confianza media/alta.
- Un monto ausente o un rol crítico de confianza baja abre el panel y destaca la
  asignación. La confianza usada es la del rol (`mapeo_extendido`), no la del
  tipo de dato; las asignaciones legacy sin score se declaran como limitación.
- El CTA del dashboard abre y desplaza directamente este panel. Las correcciones
  manuales se distinguen por rol, persisten con `saveColumnMapping` y una
  desasignación explícita ya no es revertida por la detección automática.

### Rendimiento del flujo completo
- Carga, estandarización y limpieza comparten etapas inmutables mediante un LRU
  acotado por 1,6 M de celdas; las reglas efectivas forman parte de la clave y
  `/metrics` reutiliza la limpieza ya aplicada en vez de repetir el motor.
- Las descargas repetidas desde Supabase Storage usan un caché de 5 minutos y
  45 MB, invalidado al eliminar o purgar el objeto. No cambia la autorización ni
  la validación del `storage_path`.
- Excel de una sola hoja deja de leer una muestra redundante. Una preinspección
  binaria del XML evita recorrer todas las celdas con `openpyxl` cuando no hay
  fórmulas; si existen, la auditoría detallada se conserva completa.
- La normalización textual agrupa por valor único y aparta temporalmente los
  metadatos de filas físicas para impedir copias profundas repetidas de pandas,
  restaurando la trazabilidad antes de devolver el resultado.
- Las páginas protegidas se cargan por ruta. El bundle inicial bajó de 1.044 kB
  (293 kB gzip) a 467 kB (135 kB gzip), sin retirar módulos ni controles.
- Medición local con `REQ5325` (14.917×16): flujo frío estandarizar → analizar →
  aplicar → métricas en 9,4 s; repeticiones de estandarización/limpieza en
  2–187 ms y recálculo de KPIs en ~0,5 s.

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
