# Fase 17 - Multihoja simple y análisis seguro

## Contrato

`analysis_scope` es la fuente compartida de Resumen, Explorar, Alertas,
Reportes, IA y exportaciones:

- `single`: una hoja limpia.
- `append`: dos o más hojas con columnas, tipos, mapeos y moneda compatibles;
  agrega `hoja_origen`.
- `join`: una relación `left` many-to-one u one-to-one confirmada.

El backend valida el contrato y no confía en la selección del navegador.

## Relaciones

Los candidatos comparan nombre/rol identificador, tipo, cobertura, unicidad y
solapamiento. Umbrales actuales:

- cobertura mínima por lado: 70%;
- solapamiento mínimo de claves de la hoja transaccional: 60%;
- lado maestro único: 99,5%;
- máximo dos columnas en una clave compuesta.

Many-to-many y one-to-many se bloquean. Una unión válida usa
`validate="many_to_one"`, conserva el número de filas y compara con tolerancia
numérica los totales de monto, costo y cantidad. Las métricas numéricas de la
hoja maestra nunca se agregan como hechos transaccionales.

## Exportación

XLSX abre el libro original, reemplaza solo hojas procesadas en su posición y
conserva intactas las no seleccionadas. Agrega Observaciones, Auditoría,
Manifest y, cuando corresponde, Datos_combinados o Datos_relacionados.

CSV multihoja es un ZIP con un CSV por hoja procesada, `Auditoria.csv`,
`manifest.json` y el resultado combinado/relacionado opcional. El flujo CSV de
una sola hoja conserva su contrato anterior.

## Persistencia

`0021_multi_sheet_analysis.sql` agrega a `dataset_restore_states`:
`selected_sheets`, `sheet_errors` y `analysis_scope`. El RPC v2 mantiene la
reserva monotónica y la validación de propietario de `0020`; snapshots v3
anteriores siguen legibles. La migración debe probarse en staging y no fue
ejecutada durante el desarrollo de esta rama.

## Riesgos residuales

- Los estilos de una hoja procesada se reemplazan por el formato seguro de
  exportación; las hojas no procesadas conservan estilos y fórmulas.
- La detección propone relaciones, pero nunca une sin confirmación.
- Libros extraordinariamente grandes siguen limitados por el presupuesto de
  memoria del pipeline; el procesamiento de hojas es secuencial.
