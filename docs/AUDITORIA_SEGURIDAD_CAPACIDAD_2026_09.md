# Auditoria defensiva y capacidad, septiembre de 2026

Actualizacion del 14 de septiembre: ver [cuotas gestionadas y bases de escalado](ESCALADO_Y_SEGURIDAD_2026_09_14.md). El diagnostico de retencion blanda de este documento corresponde al estado anterior.

## Dictamen

La plataforma es adecuada para una prueba piloto controlada, no para prometer capacidad empresarial ilimitada. La configuracion de Render consultada en modo lectura confirma **plan free, una instancia y un proceso Uvicorn**. El presupuesto conocido del servicio es 512 MiB. El frontend estatico en Vercel y los archivos en Supabase no consumen esa RAM mientras nadie los procesa.

Se han corregido entradas HTTP sin limite previo al parseo, validaciones JWT incompletas, seguimiento de redirecciones no acotado y formas de saturar la cola. Se mantiene **un solo calculo pesado por proceso**, tambien en los endpoints sincronos antiguos. Los calculos adicionales esperan en la cola normal; las peticiones sincronas incompatibles reciben `429` y `Retry-After: 10`, no se ejecutan simultaneamente hasta agotar memoria.

Esto es una revision defensiva de codigo y pruebas sinteticas locales, no un pentest independiente, una certificacion, una garantia de ausencia de vulnerabilidades ni una prueba de carga en produccion. No se subieron archivos ni se ejecutaron ataques contra el servicio publico. La consulta administrativa de configuracion de Render fue solo lectura; en Supabase se aplico la migracion de permisos documentada al final, sin modificar registros. No se obtuvo una serie de metricas reales de RAM/latencia: el conector no tenia un workspace seleccionado, y no se selecciono uno por inferencia.

## Cambios y evidencia

| Riesgo | Correccion | Regresion |
| --- | --- | --- |
| Un multipart enorme llegaba al parser antes de comprobar los 15 MB del archivo; JSON no tenia presupuesto global | Middleware ASGI comprueba Content-Length y bytes reales, incluso transferencia fragmentada y longitud falsa. Maximo 16 MiB por cuerpo y 2 MiB JSON. Derrama a temporal sobre 1 MiB; corta 30 segundos de inactividad entre fragmentos | Rechazo 413 antes de entrar al parser, replay exacto, longitud invalida 400 |
| JWT firmado sin vencimiento/identidad o de emisor incorrecto podia pasar ciertas validaciones | `exp`, `sub` y `aud` obligatorios. En produccion, tambien `iss` del proyecto y `role=authenticated`. Tokens de mas de 16 KiB y sujeto vacio rechazados. Mensaje de error no revela configuracion | Tokens sinteticos sin claims, audiencia/issuer/rol incorrectos y expirados reciben rechazo |
| Cache de claves JWKS individual sin TTL podia conservar una clave revocada indefinidamente | Cache del documento JWKS por 300 segundos, sin cache perpetua por clave; timeout de red de 5 segundos | Comprueba opciones del cliente y autenticacion existente |
| Google Sheets aceptaba URLs por coincidencia textual y seguia cualquier redireccion | Origen HTTPS exacto docs.google.com, ID acotado y cada salto validado antes de solicitarlo. Solo dominios oficiales Google/Googleusercontent; hasta seis solicitudes | Redirecciones a localhost, metadata IP, dominios parecidos y credenciales embebidas nunca se solicitan; CSV oficial sigue funcionando |
| Dos solicitudes simultaneas podian pasar la comprobacion de cola antes de reservar sitio; reintentar evitaba el limite | Reserva atomica y comprobacion tambien en retry. Maximo tres trabajos activos por usuario, maximo 32 por proceso | Rafaga sintetica de 30 solicitudes: tres admitidas, 27 con 429; otro usuario aun puede iniciar. Treinta solicitudes identicas producen un solo trabajo |
| Endpoints sincronos podian eludir la serializacion de la cola | Semaforo compartido entre middleware de rutas pesadas y worker. No afecta bot, health, estado, cancelacion o envios a cola | El trabajo espera mientras la ruta sincrona ocupa plaza; endpoints sync adicionales reciben 429 |
| Respuestas de datos podian ser cacheadas por intermediarios | `Cache-Control: private, no-store` cuando hay Authorization, `nosniff`, `Referrer-Policy: no-referrer` | Aserciones sobre cabeceras de respuestas |

Los tests nuevos estan en `api/tests/test_security_capacity.py`: **63 casos**. Con jobs, pipeline y procesamiento por lotes: **119 pruebas aprobadas**. La ejecucion ampliada, incluyendo seguridad anterior, configuracion, conectores, soporte y borrado de datasets, aprobo **231 pruebas** despues de la proteccion de concurrencia. `python -m pip_audit -r requirements.txt --progress-spinner off` no encontro vulnerabilidades conocidas en las dependencias resueltas. Esto no detecta vulnerabilidades aun no publicadas ni sustituye el control de versiones. La validacion integral del cambio debe volver a incluir frontend y navegacion real, especialmente sus estados de reintento ante 429.

## Controles existentes revisados

- Rutas de Storage comprueban exactamente la carpeta del usuario. Rechazan otro propietario, segmentos `..`, separadores duplicados y traversal codificado una o varias veces.
- Los endpoints de datasets, conectores y consolidacion consultados filtran por usuario; las migraciones habilitan RLS y condiciones de propiedad en tablas relevantes. La migracion 0011 revoca UPDATE general sobre profiles y permite solo columnas no privilegiadas. Revisar SQL no equivale a comprobar permisos de todas las tablas en el entorno desplegado.
- El bucket es privado en las migraciones. La clave service-role solo debe existir en backend. Al omitir RLS por esa clave, cada nuevo endpoint debe comprobar propiedad explicitamente.
- XLSX dispone de limite de expansion de 250 MiB y ratio 120; el probe sintetico de compresion extrema se rechaza antes de abrir celdas. El limite de expansion no significa que cualquier libro debajo de el quepa en 512 MiB.
- Los exports neutralizan texto que empieza por `=`, `+`, `-` o `@`, incluidos prefijos de espacios/tabulaciones. Los numeros negativos reales siguen siendo numericos. Se probo sin ejecutar ninguna formula o comando.
- El procesamiento clasico acepta CSV/XLSX y Google Sheets exportado a CSV. No equivale a soporte universal de todos los formatos o conectores de Power Query. No ejecuta macros ni reemplaza el motor de recalculo de Excel.

## Capacidad: que podemos afirmar

| Situacion | Limite o estimacion honesta |
| --- | --- |
| Personas que solo tienen abierta una pagina ya renderizada | No ocupan una plaza de pandas. No hay un numero de visitantes certificado: depende del trafico de Vercel, sesiones Supabase y solicitudes que realmente hagan |
| Procesamiento pesado simultaneo | **Uno por proceso**, coordinando lote, limpieza, estandarizacion, metricas, relaciones y restauracion que puede recalcular |
| Trabajos admitidos en cola | Hasta **32 activos por proceso**, de los cuales hasta **3 por cuenta**. Son limites de admision, no 32 analisis ejecutandose a la vez |
| Piloto operativo sugerido | Empezar con **5 a 10 usuarios activos**, mayormente leyendo resultados cacheados, y no mas de un nuevo analisis pesado cada vez. Es una hipotesis conservadora de operacion a validar, no una capacidad medida ni un SLA |
| Muchos usuarios subiendo y limpiando simultaneamente | No recomendable en el plan actual. El tiempo de espera crece con la suma del trabajo que ya esta delante |

Ejemplo de cola, no medicion del servidor: si cada trabajo tarda 120 segundos, cinco trabajos ocupan unos diez minutos en total y el quinto termina aproximadamente diez minutos despues de encolarse, sin contar nuevos costes. Si tarda 300 segundos, esos cinco requieren unos 25 minutos. La cola evita concurrencia peligrosa, pero no crea CPU ni elimina los limites de espera del cliente.

Render documenta que el plan gratuito se suspende por inactividad, no permite escalar mas de una instancia y puede reiniciarse. Los trabajos y semaforos locales no son una cola durable: un reinicio interrumpe el trabajo activo; Redis opcional comparte estado, pero las funciones encoladas siguen siendo locales. [Limitaciones oficiales de Render](https://render.com/docs/free).

## Medicion local reproducible

`python scripts/benchmark_capacity_local.py --output tmp/capacity-local.json`

Datos generados en memoria, 12 columnas comerciales, sin leer archivos privados y sin red. Maquina: Windows, Python 3.14.4, cuatro CPU logicas, 8055 MiB RAM. Proceso importado inicialmente: 115,33 MiB RSS. Una ejecucion; otras tareas del equipo pueden afectar el tiempo. La segunda carga comparte proceso/caches con la primera.

| Filas | CSV | Carga | Estandarizacion | Limpieza | Metricas | Pico RSS del proceso |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5.000 | 439.016 bytes | 0,083 s | 0,948 s | 0,568 s | 1,711 s | 143,54 MiB |
| 20.000 | 1.755.733 bytes | 0,241 s | 4,375 s | 2,357 s | 2,693 s | 180,90 MiB |

Las dos cargas conservaron todas las filas y sus ingresos coinciden con una suma independiente de los importes generados. Cincuenta consultas de limpieza ya cacheada con diez threads finalizaron en 0,021 y 0,108 segundos; p95 interno 1,685 y 9,243 ms respectivamente. **Son llamadas Python internas a cache, no latencia HTTP, red, JWT, base de datos, navegadores ni consultas frias de diez usuarios reales.**

No extrapolar linealmente el CSV sintetico a XLSX multihoja: XML, cadenas distintas, auditoria por celda, caches, joins y exports pueden multiplicar RAM. El loader limita 200.000 filas, 300 columnas y 4 millones de celdas por tabla; son topes de entrada, no promesa de procesarlos siempre dentro de 512 MiB. Las caches de frames/limpieza usan presupuestos de celdas, no un presupuesto global exacto de bytes.

## Cuantos archivos caben

La cantidad guardada depende de **Storage**, no de cuantos Excel caben simultaneamente en RAM. El limite clasico de entrada es 15 MiB; el cache de export admite hasta 64 MiB por artefacto. Original, export limpio, artefactos y snapshots deben presupuestarse por separado. Los snapshots tambien pueden consumir base de datos, no solo Storage.

La retencion configurada es 10 archivos Basico, 25 Analista y 50 Gold, con 60 dias y conservacion minima de cinco. **Es una politica blanda disparada desde el frontend, no una cuota transaccional de subida**: un cliente modificado puede omitirla. El listado usado para purgar solo recorre hasta 1000 objetos de primer nivel, no todas las subcarpetas/artefactos. No se borraron ni podaron archivos durante esta revision.

Formula de presupuesto: `documentos = floor(bytes_disponibles * 0,70 / bytes_medios_totales_por_documento)`. El factor 0,70 reserva 30%; el denominador debe incluir originales y derivados. Ejemplo hipotetico con 1 GiB disponible y derivados que triplican el original:

| Original medio | Total por documento supuesto | Documentos presupuestados |
| ---: | ---: | ---: |
| 1 MiB | 3 MiB | 238 |
| 5 MiB | 15 MiB | 47 |
| 15 MiB | 45 MiB | 15 |

Esto **no afirma que el proyecto tenga 1 GiB libre**. Hay que consultar cuota, uso real, egress y tamanos de derivados antes de fijar capacidad comercial. Supabase mide el almacenamiento por tamano total de los objetos, no por numero de documentos. [Medicion oficial de Storage](https://supabase.com/docs/guides/platform/manage-your-usage/storage-size).

## Pendientes para crecer con seguridad

### Cierre de integracion del 13 de septiembre

- Los rechazos previos al procesamiento incluyen `PROCESSING_BUSY`. El cliente
  solo reintenta ese codigo, hasta tres veces, respetando `Retry-After`, el timeout
  original y la cancelacion. No repite otras mutaciones ante errores ambiguos.
  CORS expone `Retry-After` y `Content-Disposition`; 16 regresiones frontend.
- La cola reserva explicitamente los bytes de originales retenidos: **32 MiB
  globales y 16 MiB por cuenta**, incluyendo entradas fallidas/canceladas que
  permiten reintento. Libera al completar o podar; los reintentos caducan a los
  600 segundos y se depuran con la siguiente actividad del gestor. Tres pruebas
  nuevas verifican idempotencia, presupuesto global/usuario, TTL y liberacion.
  Los limites de 32 trabajos y 3 por cuenta tambien aplican; manda el primero
  que se alcance. No es un limite exacto de RAM total: frames, resultados,
  cuerpos HTTP aun no admitidos y caches tienen presupuestos separados.
- Consulta real a Supabase: 27 tablas publicas con RLS activado. Se revisaron
  advisors y definiciones de ocho funciones. La migracion
  `20260914004735_harden_public_function_permissions` restringe ejecucion publica
  de dos triggers internos y fija `search_path=pg_catalog` en cinco funciones.
  La comprobacion posterior confirma los permisos y resultados identicos de
  normalizacion, validacion y enmascarado de RUT. No modifica registros.
- Advisors posteriores: sin los avisos de search_path mutable ni triggers
  SECURITY DEFINER ejecutables publicamente. Permanece `can_process_data()` como
  funcion intencional de autorizacion, limitada a `auth.uid()`. Las tablas
  `admin_audit` y `support_bot_articles` sin politicas cliente permanecen cerradas
  por RLS, gestionadas desde backend. No se abrieron politicas para silenciar avisos.
- Pendientes de configuracion: [proteccion de contrasenas filtradas](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)
  y [opciones MFA](https://supabase.com/docs/guides/auth/auth-mfa). No se cambiaron
  planes ni se habilitaron servicios facturables. Los avisos de permisos se
  interpretaron con la [guia del linter](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).

### Crecimiento pendiente

1. Medir p95/p99 real, cola, tiempo por trabajo y pico RSS en un entorno de staging equivalente, con cuentas sinteticas y un presupuesto de carga aprobado. Definir objetivo de latencia y cortar la prueba antes de afectar disponibilidad.
2. Aislar los calculos en un worker con memoria suficiente y cola durable antes de admitir uso comercial concurrente. No desplegar el Blueprint facturable ni cambiar de plan automaticamente.
3. Cuota dura de bytes/documentos en la operacion de subida, con reservas atomicas y limpieza segura de artefactos. La politica actual no previene abuso de Storage.
4. Limites de trafico por identidad e IP en el borde. El limite de cuerpo y el semaforo reducen impacto, pero no son una defensa DDoS ni restringen por si solos el numero de conexiones o bytes subidos simultaneamente.
5. Revisar en el entorno desplegado grants/RLS, MFA administrativo, expiracion de JWT, revocacion de sesiones, backups y una restauracion de prueba. La validacion local de JWT no invalida de inmediato una sesion revocada antes de vencer su token.
6. Antes de activar proveedores de IA facturables, cambiar las cuotas check-then-record/fail-open a reservas atomicas y definir que datos pueden salir al proveedor. Las herramientas deterministas de esta auditoria no enviaron celdas privadas a un modelo externo.

La referencia de JWT usada para contrastar issuer, vencimiento y claves es la [documentacion oficial de Supabase](https://supabase.com/docs/guides/auth/jwts). Ninguna de estas correcciones debe cambiar los importes o eliminar filas: son controles de acceso, admision y transporte; la exactitud semantica de cada fuente sigue requiriendo trazabilidad y validacion de su mapeo.
