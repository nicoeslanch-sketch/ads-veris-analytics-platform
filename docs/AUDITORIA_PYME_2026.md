# Auditoría del libro PYME desafiante 2026

Fecha: 22 de julio de 2026.

Archivos auditados:

- Original: `Prueba_PYME_Desafiante_Multihoja_ADS_VerIs_2026.xlsx` (`1906c08dc9cae986a7d5a4dfd39875a4f51d8f9d232e577e01365c9b4966be33`).
- Exportado: `Prueba_PYME_Desafiante_Multihoja_ADS_VerIs_2026_limpio.xlsx` (`fb8328d929e77291a91ba12bca3804930edbfa1881a079a9b3536b3e71b77c28`).

## Resultado de estandarización y limpieza

El motor cargó 16 hojas: `Parametros` se conservó como auxiliar y se procesaron las otras 15. El original contiene 27.084 filas en esas 15 hojas, más las 6 filas auxiliares de `Parametros`.

Se eliminaron 137 repeticiones exactas del archivo original:

| Hoja | Antes | Después | Exactas eliminadas |
|---|---:|---:|---:|
| Ventas_2024 | 4.057 | 4.029 | 28 |
| Ventas_2025 | 5.070 | 5.064 | 6 |
| Ventas_2026 | 3.041 | 3.021 | 20 |
| Productos | 304 | 300 | 4 |
| Historial_Costos | 5.414 | 5.400 | 14 |
| Inventario | 1.510 | 1.500 | 10 |
| Clientes | 810 | 800 | 10 |
| Compras | 2.215 | 2.200 | 15 |
| Gastos_Operacionales | 1.010 | 1.000 | 10 |
| Cobranzas | 3.182 | 3.162 | 20 |

`Costos_Productos`, `Proveedores`, `Sucursales`, `Vendedores` y `Metas_Mensuales` no tenían duplicados exactos y no perdieron filas.

El libro exportado conserva 26.931 filas de datos procesadas. La diferencia adicional de 16 filas frente a las 27.084 originales corresponde a estructuras que no eran observaciones empresariales (filas completamente vacías, totales o encabezados repetidos); no se imputaron ni inventaron valores para reemplazarlas.

La afirmación "se eliminaron todos los duplicados" requiere una precisión: quedaron 37 coincidencias que solo se vuelven idénticas después de normalizar (20 + 3 + 14 en las hojas de ventas). El motor las conserva deliberadamente porque podrían ser movimientos empresariales distintos; no deben borrarse sin una regla de negocio o confirmación adicional.

Los nulos, fechas imposibles, costos extremos, montos negativos y conflictos de origen permanecen señalados cuando no existe una corrección inequívoca. Esto es correcto: limpieza no significa inventar valores ni borrar observaciones legítimas.

## Correcciones descubiertas durante la auditoría

- Un porcentaje canónico como `0.018` podía reinterpretarse como `18` al reingresar el XLSX. Se hizo idempotente la semántica porcentual.
- El XLSX anteponía apóstrofes a teléfonos `+56...` y a negativos. En XLSX esos textos ya son seguros como shared strings; ahora solo se neutraliza `=`. CSV conserva la protección estricta.
- Las ventas con estado anulado se conservaban y entraban en los indicadores. Ahora permanecen en la base, pero se excluyen de ingresos, costos, utilidad, tendencias y transacciones.

## Auditoría de cálculos

Las hojas fueron reconocidas según su contenido:

- Ventas_2024, Ventas_2025 y Ventas_2026: ventas transaccionales.
- Productos y Costos_Productos: catálogos; no se presentan como ventas.
- Historial_Costos: historial temporal de costos; no se suma como gasto ni se une directamente por SKU.
- Inventario: stock, quiebres, diferencias y valorización.
- Clientes, Proveedores, Sucursales, Vendedores, Compras, Gastos_Operacionales, Cobranzas y Metas_Mensuales: perfiles operacionales adaptados.

El apilado limpio de ventas contiene 12.114 filas. La relación recomendada es:

`Ventas_2024 + Ventas_2025 + Ventas_2026` → apilar → `Costos_Productos` por `SKU_Producto`.

La unión es muchos-a-uno, conserva exactamente las 12.114 filas y los montos originales, y señala 30 filas sin correspondencia de SKU. Después de excluir 239 ventas anuladas, una recomputación independiente coincidió exactamente con el motor:

| Indicador | Resultado verificado |
|---|---:|
| Ingresos netos | $27.639.238.885 |
| Ventas con monto legible | 11.818 |
| Filas con costo conocido | 11.574 |
| Ventas pareadas ingreso+costo | 11.518 |
| Cobertura de costos | 97,5% |
| Costo conocido | $23.671.864.710 |
| Ingreso pareado | $13.344.822.963 |
| Costo pareado | $23.638.080.500 |
| Utilidad bruta pareada | -$10.293.257.537 |
| Margen bruto pareado | -77,1% |

El margen negativo no es un error aritmético del dashboard: el archivo contiene costos deliberadamente negativos, nulos, cero y extremadamente altos. La interfaz debe advertir cuántos costos atípicos concentran el resultado antes de interpretarlo comercialmente.

## Relaciones seguras y no seguras

Relaciones seguras principales:

- Ventas → Costos_Productos por SKU (costos y utilidad).
- Ventas → Productos por SKU (categoría, marca, precio de lista).
- Ventas → Clientes por ID_Cliente.
- Ventas → Vendedores por ID_Vendedor.
- Ventas → Sucursales por ID_Sucursal.
- Inventario → Productos por SKU y → Sucursales por ID_Sucursal.
- Compras → Productos/Costos_Productos por SKU, → Proveedores y → Sucursales.
- Gastos_Operacionales → Proveedores y Sucursales.
- Cobranzas → Clientes y Sucursales.
- Metas_Mensuales → Sucursales; para comparar con ventas se requiere además mes + sucursal.

Relaciones que no deben ejecutarse como unión simple:

- Ventas → Historial_Costos solo por SKU: hay varios periodos por producto; requiere una unión temporal por SKU y vigencia.
- Ventas → Cobranzas por documento: puede ser uno-a-muchos; primero hay que agregar pagos por documento para evitar multiplicar ventas.
- Inventario → Historial_Costos solo por SKU: muchos-a-muchos sin una fecha de vigencia compatible.

## Rendimiento medido

En el mismo equipo y archivo, con caché frío:

- Flujo anterior, reabriendo el libro por hoja: 18,888 s.
- Apertura única + respuestas desde etapas inmutables precargadas: 3,885 s.
- Reducción medida: 79,4%.
- Exportación XLSX completa con 15 hojas, auditoría y relación ventas→costos: 26,798 s en frío.
- Segundo clic con la misma revisión, reglas, mapeo y alcance: 0,0012 s, reutilizando exactamente los mismos bytes y sin iniciar un trabajo duplicado.

La optimización no crea snapshots ni salta validaciones. Cada `/standardize` posterior conserva su revisión independiente y su escritura protegida.
