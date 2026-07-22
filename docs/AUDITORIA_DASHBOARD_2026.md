# Auditoría de cálculos y visualizaciones 2026

Fecha de ejecución: 21 de julio de 2026. Esta auditoría se hizo contra el
código y los archivos reales suministrados; no se infirieron resultados desde
capturas ni desde el changelog.

## Qué debe aportar cada pantalla

- **Resumen** es una vista ejecutiva y operativa: responde qué pasó, qué
  requiere atención y qué decisión conviene priorizar. Limita el detalle y
  muestra señales, coberturas, estados y tendencias principales.
- **Explorar datos** es una vista diagnóstica: responde por qué pasó, en qué
  segmento ocurrió y cuál es el rango o distribución. Expone más desgloses,
  medianas, mínimos, máximos, campos disponibles y series temporales.

Los perfiles de productos, campañas, inventario y tablas maestras ya no
renderizan exactamente el mismo contenido en ambas rutas.

## Archivo avanzado: limpieza y cálculos

Archivos revisados:

- `Prueba_Avanzada_Multihoja_ADS_VerIs_2026.xlsx`
- `Prueba_Avanzada_Multihoja_ADS_VerIs_2026_limpio.xlsx`

Las ocho hojas procesadas conservan las mismas filas y columnas. Al comparar
el resultado actual de `load → standardize → clean` con el XLSX limpio, se
obtuvieron **0 diferencias en 101.841 celdas** después de normalizar únicamente
la representación de fechas de Excel, celdas físicamente vacías y el prefijo
de seguridad contra fórmulas. Los literales `NA`, `None`, `nan` y `null` se
conservan; no se confundieron con vacíos físicos. Las cinco hojas auxiliares se
mantienen sin procesar y el libro agrega Observaciones, Auditoría y Manifest.

| Hoja | Filas | Interpretación | Resultado comprobado |
|---|---:|---|---|
| Ventas_2025 | 1.826 | Ventas | Ingresos netos observados $896.250.361; 1.806 montos legibles; 15 fechas inválidas conservadas |
| Ventas_2026 | 1.825 | Ventas | Ingresos netos observados $799.475.691; 1.805 montos legibles; 14 fechas inválidas conservadas |
| Costos_Productos | 120 | Catálogo de costos | 116 SKU con costo; promedio $192.969, mediana $21.635, mínimo -$27.240, máximo $9.999.999; 5 costos a revisar |
| Productos | 120 | Maestra de productos | Categorías, marcas y estado; sin ventas inventadas |
| Inventario | 360 | Inventario | 46.983 unidades; 5 registros bajo mínimo |
| Clientes | 320 | Maestra de clientes | Distribuciones y cobertura, sin ingresos inventados |
| Proveedores | 30 | Maestra de proveedores | Ya no se clasifica como Clientes |
| Compras | 506 | Compras y abastecimiento | Total observado $3.578.262.195 y 24.788 unidades; ya no se presenta como ingreso ni utilidad |

Las dos hojas de ventas suman 3.651 filas y $1.695.726.052 con duplicados
conservados. Si se confirman solo los 25 duplicados exactos, quedan 3.626 filas
y $1.591.980.062. Eso **no** debe forzarse a los $596.878.715 del control ideal:
ese control presupone reparaciones adicionales de datos sucios, probables
duplicados y conflictos que el motor no está autorizado a cambiar en silencio.

Al apilar ventas y relacionarlas por `SKU_Producto` con `Costos_Productos`, las
filas y los ingresos se conservan. La cobertura de costos es 94,4% y quedan 24
filas con SKU no relacionado. Los valores extremos del catálogo producen
costos observados de $13.184.727.342 y una utilidad parcial negativa. La fórmula
es correcta (`Cantidad × Costo Unitario`); el dato de origen no es confiable
para interpretar margen hasta revisar los costos negativos y de $9.999.999.
Por eso el dashboard ahora señala su impacto y separa las escalas del gráfico,
pero no los elimina.

## Archivo PYME: auditoría hoja por hoja

Archivo revisado: `Prueba_PYME_Desafiante_Multihoja_ADS_VerIs_2026.xlsx`.

| Hoja | Filas | Interpretación corregida | Cálculo principal comprobado |
|---|---:|---|---|
| Parametros | 6 | Configuración auxiliar | Se recomienda conservar sin procesar; informa empresa, moneda, IVA, periodo, modelo y origen |
| Ventas_2024 | 4.057 | Ventas | $9.303.100.397 |
| Ventas_2025 | 5.070 | Ventas | $11.520.760.408 |
| Ventas_2026 | 3.041 | Ventas | $7.169.626.095 |
| Productos | 304 | Catálogo de productos | 300 SKU; precio lista promedio $68.733; 288 activos y 16 inactivos entre 304 registros |
| Costos_Productos | 300 | Catálogo de costos | Mediana $40.820; promedio $131.979; 8 costos a revisar; rango -$66.340 a $19.935.000 |
| Historial_Costos | 5.414 | Historial de costos | Costo unitario promedio $40.712; no se suma como gasto |
| Inventario | 1.510 | Inventario | Stock disponible 144.418; valor informado $6.853.493.677; 375 registros bajo mínimo |
| Clientes | 810 | Maestra de clientes | Límite de crédito total $9.948.252.996; plazo promedio 30 días |
| Proveedores | 40 | Maestra de proveedores | Plazo promedio 31,25 días |
| Sucursales | 5 | Red de sucursales | 5 registros, desglosados por región y tipo |
| Vendedores | 20 | Equipo comercial | Comisión promedio 1,77% |
| Compras | 2.215 | Compras | Total $14.464.859.302; neto $12.156.269.629; IVA $2.309.515.334 |
| Gastos_Operacionales | 1.010 | Gastos | Total $3.892.206.792; neto $3.407.282.000; IVA $437.166.820 |
| Cobranzas | 3.182 | Cobranzas | Pagos $3.698.028.099 |
| Metas_Mensuales | 90 | Metas, no ventas reales | Meta total $9.408.400.000; margen objetivo promedio 31,98%; 1.731 clientes objetivo |

Las tres hojas de ventas ahora pueden apilarse aunque `Ventas_2025` tenga la
columna auxiliar `Observación.1`. El resultado conserva las 12.168 filas y
$27.993.486.900. Al relacionarlo con costos se mantienen esas filas; hay 31 SKU
sin correspondencia y cobertura monetaria de costos de 97,5%.

### Hallazgos de calidad que no deben ocultarse

- 31 referencias de producto en ventas no existen en Productos (99,74% de
  cobertura referencial).
- 16 compras apuntan a un proveedor no presente (99,28% de cobertura).
- 20 pagos apuntan a un documento de venta no presente (99,37% de cobertura).
- 27 compras no cuadran exactamente `neto + IVA = total`; diferencia neta
  agregada de -$925.661.
- 27 gastos no cuadran exactamente `neto + IVA = total`; diferencia neta
  agregada de $47.757.972.
- 596 registros de inventario difieren en más de $2 de
  `Stock Físico × Costo Unitario = Valor Inventario`; diferencia absoluta
  acumulada $87.133.091.
- En las ventas hay inconsistencias deliberadas entre cantidad, precio,
  descuento, monto, IVA y total. El motor conserva el monto informado y no lo
  reemplaza por una fórmula inferida.
- Tras relacionar costos, 847 costos de venta son no positivos o atípicos por
  IQR y concentran 68,7% del costo absoluto. El margen resultante no es apto
  para decisión hasta revisar esos registros.

## Correcciones de presentación

- El gráfico financiero divide Ingresos y Costos/Utilidad cuando sus escalas
  difieren por cuatro veces o más; muestra una explicación y conserva los
  valores originales.
- Las agrupaciones con valores negativos usan barras divergentes y color de
  alerta. Las composiciones pequeñas y no negativas pueden usar donut.
- Cada dimensión conserva un color estable; no se pinta cada barra con un
  color arbitrario.
- Tarjetas y gráficos usan acentos por indicador, medianas y rangos. Los
  valores atípicos permanecen visibles y se señalan.
- Resumen limita el detalle. Explorar agrega desgloses, evolución, rangos y un
  diccionario rápido de columnas.

## Tiempos locales del flujo real

Medidos en Windows con Python 3.13, sobre los archivos originales y sin
escribir una copia temporal. La exportación se midió después de la limpieza,
por lo que reutiliza los resultados que ya tendría una sesión normal.

| Archivo | Clasificación | Limpieza de todas las hojas recomendadas | Métricas de todas las hojas | Exportación XLSX | Tamaño salida |
|---|---:|---:|---:|---:|---:|
| Avanzado (8 procesadas, 5 conservadas) | 1,62 s | 5,06 s | 2,34 s | 6,58 s | 1,65 MB |
| PYME (15 procesadas, `Parametros` conservada) | 3,94 s | 20,43 s | 7,60 s | 17,98 s | 4,09 MB |

Estos tiempos son una referencia de esta máquina, no un SLA de producción.
