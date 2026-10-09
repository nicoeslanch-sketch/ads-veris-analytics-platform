# Medicion por etapas del analisis durable

## Motivo

Dos filtros nuevos de un libro de 18 hojas tardaron 55,17 y 42,36 segundos en
el trabajador de produccion; sus esperas en cola fueron 0,20 y 1,08 segundos.
Esas mediciones anteriores separaban cola y ejecucion, pero no descarga,
recuperacion de hojas y calculo. No permiten atribuir la demora a la CPU.

## Instrumentacion

El trabajador emite un unico evento JSON `analysis_timing` por intento de
ejecucion, usando el canal de INFO configurado por Uvicorn en el despliegue
actual. En un trabajador standalone el operador debe configurar ese logger.
Las etapas opcionales dependen del camino ejecutado:

- `authorization`: comprobacion de capacidades antes de descargar.
- `source_download`: descarga de la fuente original.
- `analysis_cache`: busqueda, coordinacion y calculo de un analisis cacheable.
- `prepare_sheets`: recuperacion o procesamiento de hojas del manifiesto.
- `restore_clean_sheet`: intentos de recuperar artefactos limpios, acumulados.
- `compute_metrics`: calculo multihoja desde las tramas procesadas.
- `lease_rpc`: llamadas de control desde el hilo de trabajo, incluido progreso.

Los tiempos son inclusivos. Las etapas anidadas se solapan y NO deben sumarse
como si fueran partes independientes. `calls` permite distinguir una llamada
lenta de muchas llamadas pequenas. El heartbeat de su hilo independiente no
se atribuye al hilo de trabajo.

`outcome=returned` significa que el bloque de ejecucion y comprobacion final
retorno; no garantiza que el resultado ya se persistio. `outcome=raised` cubre
errores, cancelaciones y perdida de lease sin registrar sus detalles. La espera
en cola, claim y publicacion final quedan fuera de `duration_ms`.

## Privacidad y coste

Solo se admiten operaciones y etapas de listas fijas. El identificador de
traza es aleatorio, no deriva del usuario, archivo o trabajo. No se incluyen
IDs de clientes, rutas, nombres de hojas, consultas, importes, tokens ni texto
de excepciones. El numero de etapas es acotado, aunque el libro tenga muchas
hojas. No hay un registro por celda, fila o solicitud de progreso.

Fuera de una ejecucion instrumentada, el decorador de etapa no lee el reloj
ni registra nada. Un fallo del destino de logs no cambia el resultado ni
activa un reintento. Los contextos se restauran al salir y no se comparten
entre hilos. No se anaden servicios, dependencias, consultas ni planes pagos.

## Validacion

46 pruebas focalizadas aprobadas: temporizadores deterministas, agregacion,
decoradores, aislamiento entre hilos, anidacion, privacidad, fallo del logger,
y controles existentes del trabajador, ownership, cancelacion y lease.
La suite completa local aprueba 1800 pruebas (30 avisos de deprecacion).
El CI completo valida el commit antes del merge.

Esta instrumentacion no acelera por si sola la limpieza ni certifica capacidad.
Su proposito es decidir la siguiente optimizacion con tiempos observables,
manteniendo intactas las formulas, cuotas y comprobaciones de acceso.
