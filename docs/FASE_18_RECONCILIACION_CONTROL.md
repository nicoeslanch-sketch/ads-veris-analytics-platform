# Reconciliación de la Prueba de Estrés Multihoja

Fecha de verificación: 2026-07-21. Motor revisado: `0.21.4` (`0b91e28`).

## Conclusión

Los indicadores calculados por ADS Veris son reproducibles desde las celdas
visibles y legibles de las tres hojas de ventas CLP. Los totales monetarios de
`CONTROL_ESPERADO` no son reconstruibles desde el archivo entregado: la hoja
de control conserva montos declarados al generar la base, pero 203 filas ya
no contienen un monto legible (vacío, `N/D` u otro valor no interpretable).
No existe en el libro una columna paralela con los valores originales
reemplazados.

ADS Veris no debe completar esa diferencia ni usar `0`: hacerlo inventaría
datos empresariales y sesgaría ingresos, ticket, utilidad y margen.

## Evidencia por hoja

| Hoja | Visible antes | CONTROL antes | Diferencia | Visible sin duplicados | CONTROL sin duplicados | Diferencia |
|---|---:|---:|---:|---:|---:|---:|
| Ventas_Ene_Abr_2025 | $1.114.818.022 | $1.144.186.538 | $29.368.516 | $1.101.095.527 | $1.130.464.043 | $29.368.516 |
| Ventas_May_Ago_2025 | $1.053.017.351 | $1.086.769.849 | $33.752.498 | $1.037.482.041 | $1.071.234.539 | $33.752.498 |
| Ventas_Sep_Dic_2025 | $1.033.054.047 | $1.047.534.493 | $14.480.446 | $1.027.316.608 | $1.041.421.518 | $14.104.910 |
| **Total** | **$3.200.889.420** | **$3.278.490.880** | **$77.601.460** | **$3.165.894.176** | **$3.243.120.100** | **$77.225.924** |

La inferencia de causa tiene confianza alta: las filas, los conteos legibles y
los duplicados coinciden con CONTROL, mientras la diferencia solo existe en
una medida cuyo valor fue reemplazado durante la siembra de errores. No puede
probarse celda por celda porque esos valores originales ya no están en el
archivo; por eso se conserva como discrepancia declarada, no como ajuste.

## Descuentos fuera de rango

Desde `0.21.2`, una columna porcentual interpreta `20`, `20%` y `0.2` como
20%. La expectativa antigua de 360 filas fuera de rango contaba erróneamente
183 enteros porcentuales válidos. El archivo visible contiene 177 filas fuera
de 0–100% por un monto asociado de $127.950.949; cinco son copias exactas que
se conservan mientras el usuario no confirme su eliminación.

## Controles automatizados

- Las dos bases XLSX sintéticas viven en `api/tests/fixtures` y se ejecutan en
  CI sin variables privadas ni rutas locales.
- Las regresiones fijan filas, montos legibles, duplicados, ingresos visibles,
  costos derivados, relaciones, exportación, auditoría y preservación.
- Una prueba separada fija también la diferencia declarada con CONTROL para
  impedir que futuras versiones anuncien una reconciliación inexistente.
