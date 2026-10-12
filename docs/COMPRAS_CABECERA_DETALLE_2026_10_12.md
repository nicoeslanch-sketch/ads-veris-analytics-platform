# Compras por cabecera y detalle

## Cambio del motor 0.33.0

El modelo empresarial reconoce cabeceras y lineas de compra repartidas en
varias hojas mediante ID de compra explicito. Publica un indicador separado,
`compras_valorizadas`: cantidad por costo unitario declarado, en compras no
anuladas con fecha y estado verificables. Incluye pendientes.

No se presenta como compras netas de IVA/descuentos, pagos, costo de ventas ni
salida de caja. `compras_netas` conserva su definicion anterior y permanece no
disponible cuando no existe ese importe en la fuente. Las fechas del nuevo
indicador provienen de compras, no de las fechas de venta.

## Controles

- Lookups contra IDs unicos, sin join que multiplique las lineas.
- Cabeceras identicas no multiplican compras. Las contradictorias se excluyen.
- Las copias de lineas se conservan segun la decision de limpieza y se advierten.
- Conflictos de ID/linea, cantidades o costos invalidos, fechas/estados
  desconocidos y lineas huerfanas no se rellenan con cero.
- Se conserva el subtotal verificable y se marca parcial si falta evidencia.
- Se identifican hojas y filas originales de relaciones sin correspondencia.
- Monedas incompatibles, columnas de moneda ambiguas y segmentaciones sin
  contrato de compras impiden publicar un total general como si fuera filtrado.
- Se aplican los filtros temporales a las fechas de cabecera.
- Los importes fuera del rango numerico admitido no se serializan como infinito.

La cobertura de lineas no equivale a cobertura de documentos: una cabecera
sin detalle puede dejar el resultado parcial aunque las lineas tengan ID.
No se usa el maestro de productos para inventar costos faltantes.

## Bot

Responde con el indicador publicado de compras valorizadas cuando no existe
un total neto y la pregunta es general. Una solicitud explicita de compras
netas, incluida la continuacion "y el total", no recibe otro tipo de importe.
Explica la diferencia con pagos y muestra las fechas de las compras.
El normalizador preserva `pagado`, `pagados`, `pagada`, `pagadas` y `pague`,
evitando convertirlos en palabras de tiempo como `pasado`.

## Verificacion

- Pruebas sinteticas en `api/tests/test_purchase_documents.py`, junto con las
  pruebas existentes de indicadores, bot y contratos de despliegue.
- Bateria de conversaciones: `scripts/exercise_assistant.py`.
- Recorrido local del libro autorizado con `scripts/audit_challenging_workbook.py`.
- Referencia independiente en Decimal/openpyxl con
  `scripts/audit_purchase_lines.py`, sin importar el motor ni ajustar cifras
  al libro de control. Compara total y numero de lineas elegibles.
- El libro de control no se sube. Datos, transcripciones e importes del cliente
  permanecen en `artifacts/`, fuera del repositorio publico.

La reconciliacion valida este indicador y esta estructura de compras. No
certifica todos los KPIs del libro, todos los esquemas posibles, capacidad
comercial, restauracion externa ni requisitos legales. No cambia pagos, IA
de pago, permisos, RLS, infraestructura o migraciones.
