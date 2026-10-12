# Calculos por producto, cliente y otras dimensiones

## Cambio

`business._group_profit` deja de construir un DataFrame por cada grupo.
Reutiliza las columnas y selecciona posiciones, conservando los tipos de
Pandas, el orden original de suma y la eliminacion de nulos antes de sumar.
Tambien reutiliza los ingresos positivos ya calculados.

No se usa una suma agrupada distinta: cambiar el algoritmo de suma puede
alterar el redondeo en centavos. Se mantienen filas sin importes, cobertura
de costos, costos pareados, devoluciones, empates, orden y limites de rankings.
No cambia la limpieza, el archivo descargable ni el alcance de relaciones.

## Pruebas

- 83 casos nuevos comparan el resultado exacto con una referencia congelada
  del calculo anterior, sin tolerancia numerica.
- Incluyen enteros, decimales, tipos anulables, numeros grandes, cancelacion
  numerica, nulos, devoluciones, indices repetidos o desordenados y empates.
- Comprueban que no se muten las fuentes y que no se construyan DataFrames
  por grupo. Se mantienen las pruebas de filtros y relaciones del pipeline.

## Medicion local

Caso sintetico de 9.000 ventas, tres periodos y una tabla de costos, con
red bloqueada. Cada tanda tiene tres ejecuciones sin profiler:

| Tanda | Mediana anterior | Mediana optimizada | Reduccion |
| --- | ---: | ---: | ---: |
| Primera | 7,8975 s | 3,9548 s | 49,9% |
| Repeticion | 6,2016 s | 4,9134 s | 20,8% |
| Seis ejecuciones por version | 6,9989 s | 4,3126 s | 38,4% |

Las doce ejecuciones producen exactamente el mismo SHA-256 del resultado
completo: `63350b21982da0643d40e65f49bca00b73854c8e3f9b4cae5792a7899410bb93`.
Los importes tambien coinciden con una suma independiente de ventas y costos.
Comando base: `python scripts/benchmark_business_pipeline.py --rows-per-sheet 3000 --runs 3 --output artifacts/performance-20261012/after.json`.
La repeticion anterior sustituye temporalmente `_group_profit` por la funcion
`reference` de `tests/test_grouped_profit_equivalence.py`, solo en el proceso
local de medicion. Los recibos completos quedan fuera del repositorio publico.

Esto mide calculo sobre tablas ya limpias en un equipo local con Python 3.14.
No incluye subida, XLSX, red, cola ni limpieza, no garantiza esa mejora en
Render y no certifica usuarios simultaneos. La variacion entre tandas impide
presentar una cifra de latencia garantizada. No se contrataron recursos ni
se realizaron pruebas de carga sobre clientes reales.
