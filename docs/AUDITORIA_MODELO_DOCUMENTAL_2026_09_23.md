# Auditoria del modelo cabecera-detalle

## Correcciones de esta entrega

- El mapeo monetario rechaza IDs, estados y otros atributos de documentos.
- El neto de linea tiene prioridad sobre totales con impuestos; el numero de
  linea de una transaccion no se usa como categoria de producto.
- Se integra cabecera de venta -> lineas -> maestros mediante claves explicitas.
  No se unen tablas por semejanza de texto ni se multiplican las lineas.
- Cabeceras identicas sirven como una sola referencia. Las contradictorias,
  IDs inexistentes y atributos incompatibles quedan excluidos del analisis
  valido y conservados en la base/exportacion, con ubicaciones para revisar.
- Documento + numero de linea define la identidad cuando existe: dos lineas
  distintas del mismo producto son operaciones legitimas.
- Los costos unitarios declarados en la transaccion prevalecen sobre el catalogo
  actual. Un costo invalido no se sustituye silenciosamente por cero.
- Los graficos generales del modo negocio reciben fecha y estado de cabecera,
  y excluyen las mismas lineas sin referencia valida que el modelo empresarial.
- Las metas porcentuales con encabezados CamelCase no se suman como dinero.
  El bot distingue metas de resultados y mantiene las preguntas de seguimiento.
- Las cabeceras sin importes no se presentan como una maestra de clientes;
  el bot explica cuando es necesario vincularlas con las lineas de venta.
- El selector de relaciones no pierde una respuesta valida por el ciclo de
  montaje/verificacion de efectos de React StrictMode.

## Evidencia reproducible sin datos de clientes

`api/tests/test_document_line_model.py` genera cabeceras y detalles sinteticos.
Comprueba importes, costos, anulaciones, duplicados conservados, claves ambiguas,
periodos, entradas inmutables y concordancia entre graficos y analisis.

`frontend/e2e/document-model.spec.ts` carga ese libro por la interfaz real,
estandariza, limpia y abre Vision del negocio en escritorio y movil.

`scripts/audit_pyme_control.py` permite contrastar un libro local con un control
local usando Decimal y openpyxl, sin importar el motor de produccion ni enviar
archivos a un servicio. El control nunca se usa para rellenar datos originales.

Los resultados, exportaciones y nombres de los libros aportados por el usuario
permanecen en `artifacts/`, fuera del commit publico.

## Limites pendientes

Este cambio no afirma soporte universal para cualquier modelo relacional.
La nueva union automatica se limita a IDs explicitos de ventas y atributos
compatibles; no inventa relaciones ni repara cantidades/descuentos alterados.

Todavia requiere ampliacion el modelo de CxC, las compras con detalle separado
y la valorizacion por cortes de inventario del caso de auditoria. La comparacion
completa contra todos los KPIs del control no esta terminada.

El ensayo de respaldo sintetico y la prueba de capacidad aislada de la entrega
anterior no sustituyen un respaldo externo real ni certifican usuarios de Render.
Pagos reales continúan apagados; esta entrega no contrata infraestructura.
