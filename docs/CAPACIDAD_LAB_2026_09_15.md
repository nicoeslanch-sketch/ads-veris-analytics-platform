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
300 trabajos. Drenaje maximo de 180 segundos. Es una carga cerrada controlada,
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

## Correcciones encontradas al preparar el entorno

La migracion de permisos `20260914004735` asumia que existia
`public.rls_auto_enable()`, una funcion que puede instalar la plataforma alojada
pero no viene en una base nueva del CLI. Se hizo condicional solo esa revocacion:
si existe se conserva el endurecimiento; no se crean funciones vacias ni se
rebajan permisos. El cambio permite reproducir el esquema desde cero; no exige
volver a aplicar esa migracion en la base de produccion ya migrada.

El consumidor externo incrementaba la espera tambien al encontrar una cola
vacia, hasta 60 segundos. Ahora mantiene el intervalo configurado en una cola
sana (5 segundos por defecto, 1 en el laboratorio). El backoff hasta 60 segundos
se conserva para errores de conexion y se reinicia al recuperar el servicio.
Tres pruebas cubren inactividad prolongada, fallos y recuperacion.

Regresion local tras esos cambios: 1.131 pruebas backend aprobadas. El CI de
`9ade9a8` tambien aprobo backend, frontend, build, E2E y dependencias.

## Primera ejecucion

[Run 35039757641](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/35039757641),
commit `9ade9a8`, runner Linux de 4 CPU, 5 cuentas, CSV de 4.000 filas cada uno:

| Medida | Resultado |
| --- | ---: |
| Analisis correctos / admitidos | 40 / 40 |
| Ventana observada | 120,29 s |
| Espera en cola p95 | 3,135 s |
| Calculo p95 | 0,929 s |
| Tiempo completo p95 | 4,723 s |
| Admision HTTP p95 | 61,997 ms |
| Consulta de estado HTTP p95 | 94,241 ms |
| Pico de RSS API / consumidor individual | 187,74 / 156,80 MiB |
| Recuperacion tras caida del consumidor | 121,784 s, intento 2 |

Todos los controles de aislamiento, cuota de cola, cancelacion, reinicio e
idempotencia pasaron. El 429 fue provocado y esperado. Cero peticiones de carga
a produccion y cero archivos de clientes leidos.

Esta primera version tenia un tope de 40 trabajos, por lo que parte de la
ventana quedo sin nuevas admisiones. Sus 19,952 trabajos/minuto son el ritmo
observado de una prueba acotada, NO la capacidad maxima del sistema. La siguiente
version mantiene carga durante la ventana (hasta 300 trabajos) y conserva las
mediciones antes de la eliminacion normal de resultados antiguos en la cola.

## Prueba ampliada del 16 de septiembre

[Run 35079093577](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/35079093577),
commit `6b2dac5`, runner Linux de 4 CPU. Diez cuentas independientes y diez CSV
sinteticos de 10.000 filas cada uno; filtros sucesivos, no 300 importaciones nuevas.
La API y dos consumidores son procesos separados en el mismo runner, no maquinas
de Render con recursos dedicados. Autenticacion, base de datos y Storage reales.

| Medida | Resultado |
| --- | ---: |
| Analisis correctos / admitidos | 300 / 300 |
| Duracion de la carga | 300,186 s |
| Ritmo ofrecido y completado aproximado | 60 trabajos/minuto |
| Espera en cola p50 / p95 / maxima | 2,389 / 3,648 / 10,584 s |
| Calculo p50 / p95 / maximo | 0,423 / 0,515 / 1,590 s |
| Tiempo completo p50 / p95 / maximo | 3,377 / 4,507 / 11,538 s |
| Admision HTTP p95 | 55,616 ms |
| Consulta de estado HTTP p95 | 116,290 ms |
| Pico RSS de API / consumidor individual | 217,99 / 196,64 MiB |
| Recuperacion de caida | 122,052 s; mismo ID; intento 2; total correcto |

Pasaron aislamiento entre cuentas, JWT obligatorio, denegacion de RPC privada,
idempotencia, persistencia tras reiniciar la API, cancelacion, cuota por cuenta
y coordinacion de los dos consumidores con un solo trabajo pesado simultaneo.
El unico 429 fue solicitado por el escenario de cuota, no un fallo inesperado.
Las 1.873 consultas de estado registradas respondieron HTTP 200. No se tocaron
datos de clientes ni se enviaron peticiones de carga a produccion.

El escenario cumple los objetivos numericos de latencia de este laboratorio.
No permite afirmar cuantos usuarios soporta un plan Render: faltan red real,
limites de CPU/RAM del plan, XLSX complejos, importaciones/exportaciones repetidas,
mezcla realista y mayor duracion. El RSS medido no incluye Supabase ni demuestra
el margen de memoria de archivos grandes. No se cambio la concurrencia global.

Evidencia completa, sin credenciales y conservada en Git:
[primera prueba](evidence/capacity-lab-35039757641.json) y
[prueba ampliada](evidence/capacity-lab-35079093577.json).

Publicacion verificada: Vercel Ready en `6b2dac5`; API Render en `65e3553`, el
ultimo cambio de codigo de API de esta etapa. Los commits posteriores modifican
laboratorio/documentacion. Produccion conserva `embedded`: no se contrato ni se
activo un servicio de procesamiento externo. En una comprobacion de disponibilidad
la primera consulta de version agoto 30 segundos y la siguiente respondio bien;
no se atribuye una causa sin telemetria y no cuenta como prueba de latencia cloud.

## Criterios propuestos para el piloto, todavia no certificados

Estos umbrales son objetivos internos de aceptacion, no promesas contractuales.
El laboratorio informa tiempos; no aprueba automaticamente un plan comercial.

| Control | Objetivo inicial |
| --- | --- |
| Totales y aislamiento | Cero resultados incorrectos o acceso entre cuentas |
| Tareas admitidas | Cero tareas perdidas o duplicadas tras reinicios |
| API ligera: admision y consulta de estado | p95 menor de 1 segundo |
| CSV de 10.000 filas del escenario definido | p95 completo menor de 30 segundos |
| Recuperacion del consumidor interrumpido | Menos de 180 segundos con infraestructura disponible |
| Recursos de cada instancia elegida | Pico menor del 75% de su limite de RAM; sin OOM ni reinicios |
| Errores HTTP inesperados bajo carga aceptada | Menos de 0,1%; informar por separado los 429 esperados |

Antes de aprobar: repetir en staging separado durante al menos dos horas, con
datos sinteticos representativos, flujos frios/calientes y una mezcla explicita
de lectura, subida, limpieza y descarga. Medir errores, admisiones/rechazos,
cola, memoria total y CPU por instancia. Revisar percentiles por tipo de archivo,
no mezclar lecturas de cache rapidas con importaciones lentas en un solo promedio.

Incluir XLSX de una y varias hojas, formatos heterogeneos, archivos cercanos al
limite permitido, concurrencia entre cuentas y descargas tras cambiar de proceso.
Los tiempos de XLSX grandes necesitan objetivos propios obtenidos de esa prueba;
no se les asigna el umbral del CSV pequeno. Mantener 1 plaza de calculo hasta
demostrar margen de RAM y CPU antes de aumentar a 2.

Un resultado satisfactorio certificaria solamente la configuracion, mezcla,
tamano, concurrencia y duracion efectivamente ensayados. No demuestra seguridad
absoluta ni capacidad ilimitada, y no sustituye auditoria ni prueba de respaldo.
