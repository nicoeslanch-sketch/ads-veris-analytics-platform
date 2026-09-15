# Rendimiento del analisis empresarial

## Cambio

La ruta de Vision del negocio ejecutaba `analyze_business_workbook` para detectar
el perfil de servicios y la volvia a ejecutar al publicar el analisis de otros
negocios. Se reutiliza el primer resultado, incluido el caso no compatible.
No se cambian las formulas, los filtros, la limpieza ni el tratamiento de IDs.
La cobranza fuera del modo empresarial sigue calculandose cuando corresponde.

Se agregaron puntos de progreso y cancelacion entre el analisis empresarial y
las metricas generales. Una cancelacion puede evitar la siguiente fase; no
interrumpe una operacion indivisible de pandas.

## Comparacion Local

Referencia anterior: commit `12987cf`. Tres ejecuciones sin profiler por version,
con un proceso nuevo para cada version. Datos sinteticos: 12.000 ventas, tres periodos y un maestro
de 300 costos por SKU. Python 3.14.4, equipo local con 4 CPU logicas.

| Medida | Antes | Despues |
| --- | ---: | ---: |
| Ejecuciones del analisis empresarial por consulta | 2 | 1 |
| Tiempo mediano de calculo | 9,2656 s | 5,7829 s |
| Tiempo de cada repeticion | 9,2656 / 8,7478 / 10,5342 s | 5,9308 / 5,7748 / 5,7829 s |
| RSS maximo observado | 192,53 MiB | 183,31 MiB |

Reduccion observada de tiempo: **37,6%**. Es la etapa que usa tablas ya limpias,
no el tiempo completo de importar, limpiar, descargar o abrir un Excel en Render.
Las lecturas de RSS son muestras, no una garantia de memoria maxima.

Los resultados completos serializados conservaron el mismo SHA-256:
`706cfe7739d0acfeeb4fea0b967fcfff0b452e8059a78af53e28b8bb2fc9bf94`.
Tambien se verificaron sumas independientes: ingresos 41.316.000 y costo 8.916.000,
sin perder ni multiplicar filas. Esa igualdad valida esta muestra sintetica;
las regresiones separadas cubren filtros, datos incompletos y claves conflictivas.

Reproduccion desde la raiz del repositorio:

```powershell
python scripts/benchmark_business_pipeline.py --rows-per-sheet 4000 --runs 3 --output tmp/business.json
```

El argumento `--compare tmp/business-before.json` exige identidad de resultados
con una medicion anterior. La medicion de tiempos excluye el profiler, que se
ejecuta por separado para localizar las siguientes partes costosas.

## Conexiones HTTP Locales

Prueba aislada con la API real en loopback: dos cuentas sinteticas envian un CSV
de 4.000 filas cada una, mientras diez clientes consultan version, configuracion
del bot y estado de trabajos. Sesenta consultas, todas con respuesta 200;
ambas admisiones devolvieron 202 y ambos trabajos terminaron con el ingreso
esperado. Consultar un trabajo desde la otra cuenta devolvio 404.

Latencia mediana: 69,81 ms; p95: 532,05 ms. RSS maximo muestreado del arbol de
procesos de la API: 190,45 MiB. No se enviaron peticiones a produccion, no se
subieron archivos a Storage y no se leyeron datos de clientes.

```powershell
python scripts/benchmark_http_local.py --rows 4000 --clients 10 --output tmp/http-local.json
```

El ejecutable usa un puerto libre en 127.0.0.1, credenciales de prueba efimeras
y rechaza conexiones salientes no locales. Cierra el servidor al finalizar.
No acepta una URL de produccion. Limita clientes, filas y tiempo de espera.

## Regresiones

- Backend: 1.094 pruebas aprobadas; 30 avisos de deprecacion de dependencias.
- Frontend: 190 pruebas aprobadas.
- Navegador: 19 recorridos aprobados; una auditoria opcional de archivo real
  omitida porque requiere un libro local y una referencia independiente.
- Sonda HTTP repetida con 100 filas y dos clientes tras ajustar el cierre del
  proceso: dos trabajos completos, 60 consultas correctas y aislamiento 404.

La bateria del navegador incluye limpieza multioja, exportacion, relaciones
muchos-a-muchos bloqueadas, filtros, contexto del bot y ajuste en movil.

## Limites

Diez conexiones locales no equivalen a diez usuarios comerciales certificados.
La prueba HTTP usa el camino local de trabajos, no PostgreSQL, Storage, JWT
remoto ni el consumidor durable. Tampoco reproduce la CPU compartida de Render
Free, arranques en frio, archivos hostiles ni una carga sostenida de horas.

Falta medir el despliegue de staging con cola persistente y worker separado,
mezclas representativas de archivos, ocupacion de RAM, rechazos y espera en cola.
No se aumentaron instancias, cupos ni planes contratados con esta optimizacion.
