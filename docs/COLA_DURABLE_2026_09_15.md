# Cola persistente de analisis

## Alcance

Los endpoints de trabajos de metricas, estandarizacion por lote, limpieza por
lote y exportacion multihoja encolan referencias a fuentes guardadas. El cuerpo
del Excel ya no se descarga ni se conserva en una funcion Python mientras espera.
Se reutilizan las mismas funciones de calculo, reglas, manifiestos, revisiones,
filtros y decision sobre duplicados. No se simplifica la limpieza.

Fuentes enviadas directamente como multipart, sin dataset/Storage persistente,
y endpoints sincronicos conservan su camino anterior. Esta entrega no los
convierte en trabajos recuperables ni garantiza que todo consumo pesado salga
de la API. Tampoco acelera por si misma pandas en una CPU compartida.

## Funcionamiento

- Migracion `20260915013758_durable_analysis_queue`: dos tablas privadas con RLS
  y un RPC SECURITY INVOKER accesible solo a service_role. La API toma el usuario
  del JWT; no se acepta una identidad de propietario elegida por el navegador.
- Admision atomica inicial: 32 trabajos activos globales, 3 por cuenta y 1 en
  ejecucion. El ultimo limite se guarda en PostgreSQL, no depende del numero de
  procesos. Un worker no reclama trabajo mientras el semaforo local este ocupado.
- Se comprueban dataset, propietario, ruta y objeto de Storage antes de encolar
  y al ejecutar. El worker vuelve a comprobar el plan antes de descargar.
- Lease de 120 segundos, renovado cada 20; una caida permite reclamar de nuevo.
  Tres intentos maximos. La renovacion y publicacion exigen el token vigente;
  un resultado tardio de otro intento se rechaza.
- Cancelacion cooperativa entre fases. Un calculo indivisible de pandas no se
  interrumpe instantaneamente. A los 20 minutos se solicita detener el intento.
- SIGTERM deja de aceptar trabajo. La recuperacion reejecuta las fases usando
  las mismas opciones y revisiones, no reanuda una celda exacta. No se promete
  ejecucion exactamente una vez de todos los efectos secundarios.
- El navegador sigue el mismo identificador ante fallos transitorios del estado.
  Al completar se invalida la cache de restauracion de la API que recibe el sondeo.
- Una exportacion en un worker no anuncia que esta lista si no existe metadata
  persistente valida. Si guardar falla por cuota, se informa; el camino de
  descarga sincronica conserva su posibilidad de calcular el archivo en memoria.

## Presupuestos y retencion

Opciones: 256 KiB por trabajo; resultado: 2 MiB; resultados guardados: 32 MiB en
total. Se conservan hasta 64 terminales al admitir otro trabajo, y se depuran los
terminales de mas de 24 horas en operaciones de admision/claim/reintento.
Es una cache operativa acotada, no un archivo historico ni una cuota de todas las
tablas PostgreSQL. No se borran fuentes ni snapshots al depurar esta cola.

La seleccion favorece cuentas que no han ejecutado recientemente y no permite
dos trabajos simultaneos de la misma cuenta. No es una garantia contractual de
latencia ni sustituye mediciones con trafico representativo.

## Modos de despliegue

`ANALYSIS_DURABLE_MODE=auto` habilita PostgreSQL y un consumidor embebido solo en
produccion; desarrollo conserva la cola local. El consumidor embebido mantiene
la recuperacion de trabajos, pero comparte CPU/RAM con la API. En Render Free
un servicio dormido no procesa hasta que despierta: no es un worker siempre activo.

`external` deja la API encolando sin consumidor interno. El comando
`python -m app.analysis_worker` consume la misma cola desde otro servicio.
`deploy/render-analysis-worker.yaml` es una plantilla NO aplicada; no contratar
el servicio sin aprobacion del presupuesto. Desplegar primero el worker con la
misma version y luego cambiar la API a external. La admision central sigue en
una ejecucion hasta validar mayor concurrencia y RAM.

`off` conserva el comportamiento local para nuevas peticiones. Los IDs `dq_`
siguen consultandose y cancelandose en PostgreSQL. Para drenar pendientes hay que
mantener un consumidor; no borrar las tablas como mecanismo de rollback.

Aplicar la migracion antes de desplegar la API. Si PostgreSQL no esta disponible,
la admision falla con 503; no crea silenciosamente otra cola local con duplicados.
`/version` declara `analysis_worker_mode` y la migracion esperada.

## Verificacion

Regresion local: 1.047 pruebas backend y 190 frontend aprobadas; build de
produccion correcto; Playwright 19 aprobadas y 1 auditoria opcional omitida.
Los escenarios incluyen multihoja, descarga, relaciones y conversaciones del bot.

Pruebas SQL reales, en una transaccion revertida: idempotencia, propiedad,
limite global de ejecucion, validacion de fuente, recuperacion tras lease vencido,
rechazo del resultado del intento anterior, cancelacion contra finalizacion,
reintento y cuota de trabajos por usuario. No se leyo contenido de archivos ni
se dejaron trabajos sinteticos en produccion. anon/authenticated no pueden
ejecutar el RPC ni usar el esquema privado.

Pruebas Python: admision sin descargar Excel, contratos de las cuatro rutas,
preservacion de opciones/revision, exclusion con trabajos locales, perdida de
lease, cancelacion, cierre, error sin filtrar informacion y exportacion durable.
Pruebas frontend: recuperacion del sondeo tras 503, resultado ya disponible,
error explicito y cancelacion del mismo ID. Antes de escalar instancias falta
un benchmark aislado de carga y memoria, ademas de MFA y limites distribuidos
de solicitudes. Ver [MFA](https://supabase.com/docs/guides/auth/auth-mfa).
