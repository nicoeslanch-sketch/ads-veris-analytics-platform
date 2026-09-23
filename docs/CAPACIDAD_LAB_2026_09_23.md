# Carga sostenida con Excel multioja

Ejecucion: https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/35844582696
Commit: 60f74e3b30d40eb9f6b41412ffd2863bfe6d9e01. Resultado: aprobado.

## Configuracion medida

Runner GitHub Linux de 4 CPU. Supabase local desechable, API separada de workers,
5 cuentas con JWT real y 5 archivos XLSX sinteticos. Cada libro: 4.000 ventas
repartidas en tres hojas y una maestra de productos. Incluye IDs con espacios,
fechas texto y montos texto con simbolo monetario. No se subieron archivos de
clientes ni se enviaron solicitudes a produccion.

Dos consumidores respetando un limite GLOBAL de un calculo simultaneo, cola
de 32 trabajos y hasta 3 pendientes por cuenta. Carga cerrada: una solicitud
pendiente por cuenta, minimo diez segundos entre inicios, durante 900 segundos.
Los calculos usan filtros variables y se comparan con totales independientes.

## Resultados

| Medida | Resultado |
| --- | ---: |
| Trabajos completados / enviados | 435 / 435 |
| Duracion observada | 902,69 s |
| Trabajos por minuto | 28,91 |
| Latencia total mediana / p95 / maxima | 2,70 / 4,36 / 9,17 s |
| Espera en cola mediana / p95 / maxima | 1,78 / 3,27 / 7,21 s |
| Procesamiento mediana / p95 / maximo | 0,61 / 0,67 / 1,89 s |
| Estandarizacion de libro, mediana / maxima (5) | 1,67 / 1,78 s |
| Limpieza de libro, mediana / maxima (5) | 1,67 / 2,23 s |
| Admision HTTP p95 | 59,84 ms |
| Consulta de progreso HTTP p95 | 92,70 ms |
| Pico RSS API / worker medido | 198,00 / 174,26 MiB |

Las 435 sumas esperadas coinciden. Estandarizacion, limpieza y persistencia de
las cuatro hojas pasaron. La API reiniciada conservo la cola. Tras matar un
worker, el trabajo se recupero en 122,77 s (lease real de 120 s), intento 2,
sin perderlo ni alterar el total. Un rechazo 429 fue provocado deliberadamente
para comprobar el limite por cuenta. Acceso anonimo, cruzado entre cuentas y
RPC privadas quedaron bloqueados.

## Que permite concluir

La cola y el motor mantuvieron correccion con cinco cuentas activas en ESTE
escenario. Se midio latencia, aislamiento, recuperacion y limites compartidos.
La arquitectura permite separar API/worker sin contratar una reescritura.

No certifica cinco usuarios comerciales en Render ni permite multiplicar este
numero por RAM o precio. El runner tiene CPU, red local y base distintas. El RSS
es por proceso, no suma de todos los servicios ni memoria total de Supabase.
No mide el XLSX real de 19 hojas, exportaciones masivas, Google Sheets, consultas
IA externas o sesiones de navegador completas. Tampoco demuestra margen de
capacidad: la tasa ofrecida esta controlada, no es una prueba de saturacion.

Siguiente certificacion: misma prueba en un entorno aislado con el plan objetivo,
mezcla representativa de archivos y operaciones, rampas y carga sostenida mayor,
presupuesto/ventana aprobados y criterio previo de latencia y errores. No se
debe hacer una prueba destructiva de saturacion en el servicio de clientes.
