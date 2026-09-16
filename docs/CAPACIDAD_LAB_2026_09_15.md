# Laboratorio aislado de capacidad

## Alcance

El workflow manual `Capacity lab` prepara Supabase local en un runner temporal
de GitHub: PostgreSQL, Auth, PostgREST y Storage reales, con todas las migraciones
del repositorio. No utiliza secretos, cuentas, archivos ni endpoints de produccion.
No contrata servicios. El repositorio es publico; se usa un runner Linux estandar.

La API y los consumidores ejecutan procesos distintos con
`ANALYSIS_DURABLE_MODE=external`, autenticacion real y planes activados.
La configuracion de entorno es `development`, sin bypass. No prueba TLS, CORS
de produccion, red de Render, latencia geograficamente distribuida ni facturacion.

## Comprobaciones

- Subida administrada real y reservas de almacenamiento con cuentas sinteticas.
- Persistencia del trabajo despues de reiniciar la API; identidad idempotente.
- Lectura, cancelacion y reintento de trabajos ajenos rechazados.
- RPC privada inaccesible con JWT de cliente; sin token, HTTP 401.
- Tres trabajos activos por cuenta: el cuarto devuelve 429 y Retry-After.
- Caida deliberada de un consumidor despues de tomar una tarea real. Se espera
  el vencimiento real de su lease de 120 segundos. Otro consumidor termina el
  mismo trabajo en el segundo intento y conserva el total correcto.
- Dos consumidores compiten respetando el limite global de un trabajo activo.
- Cuentas concurrentes consultan estados y ejecutan filtros distintos sobre CSV
  sinteticos. Todos los ingresos se comparan con un total independiente.

## Carga y metricas

Parametros acotados: 2-10 cuentas, 100-10.000 filas/CSV, 60-300 segundos de carga.
Un trabajo pendiente por cuenta, al menos 10 segundos entre inicios y maximo
40 trabajos. Drenaje maximo de 180 segundos. Es una carga cerrada controlada,
no una busqueda del punto de saturacion ni una prueba de muchas horas.

El artefacto JSON registra p50/p95/max de HTTP, espera en cola, ejecucion y tiempo
total, memoria RSS maxima por proceso, resultados y recuperacion. El percentil
usa rango mas cercano. La memoria no incluye los contenedores de Supabase.
La carga sostenida usa el worker ya iniciado: puede reutilizar caches del archivo,
pero cambia filtros; no representa una importacion nueva en cada solicitud.

## Ejecucion

Desde GitHub Actions ejecutar `Capacity lab`, o con GitHub CLI:

```sh
gh workflow run capacity-lab.yml -f clients=5 -f rows=4000 -f seconds=120
```

El runner termina procesos propios y elimina la infraestructura temporal incluso
si falla la prueba. Los artefactos publicados contienen solo metricas sinteticas,
no tokens, correos, claves de servicio ni fuentes. Rechaza destinos remotos y
una base local que ya tenga usuarios, datasets u objetos.

## Interpretacion

Pasar esta prueba demuestra funcionamiento de la arquitectura separada en ese
entorno; NO certifica una cantidad comercial de usuarios simultaneos.
Antes de ofrecer un SLA: aprobar presupuesto, crear staging separado, repetir
con XLSX multihoja representativos y carga sostenida mas larga, medir memoria
total y latencia de red, y comprobar backup/restauracion. No aumentar workers
ni cuotas de produccion solo a partir de estos resultados.
