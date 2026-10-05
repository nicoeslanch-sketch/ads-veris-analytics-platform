# Catalogo: filas, productos y monedas

## Hallazgo reproducido

En la interfaz publicada, despues de consultar cuantos productos habia,
preguntar cuantos estaban inactivos repetia el resumen de precios/costos.
Ademas, el total de productos distintos y el conteo de estados por fila se
presentaban sin aclarar que usaban unidades de conteo diferentes.

## Correccion

- El bot responde por estado, entiende errores y palabras juntas, conserva el
  contexto de porcentajes y no usa el total general para otro periodo o segmento.
- Porcentaje del bot: filas con ese estado / todas las filas del catalogo.
  Los estados desconocidos permanecen en el denominador y se informan.
- Explorar identifica explicitamente cuando su porcentaje usa solo los estados
  reconocidos. Ninguno se presenta como porcentaje de productos unicos.
- El motor publica numero de registros, columna que define productos distintos
  y estados sin reconocer. No elimina ni fusiona duplicados sin autorizacion.
- Estados, categorias, marcas, promedios y sumas unitarias conservan su calculo
  por fila. Las etiquetas dicen una unidad por fila, no por SKU.
- Inactivo en la maestra no demuestra meses sin ventas ni justifica retirar
  automaticamente un producto.
- Los ejes compactos usan la misma moneda que tarjetas/tooltips. Una prueba con
  UF detecto que los ejes heredados imprimian pesos; el formateador comun se
  corrigio tambien para USD y otras monedas admitidas.
- Las cifras usan el componente compartido que ajusta el tamano sin partir un
  numero en dos lineas. Los graficos del catalogo no dependen de una animacion
  para tener sectores y barras visibles al exportar o capturar una vista larga.
- Motor 0.32.6 invalida resultados antiguos para publicar el nuevo contrato.

## Pruebas

- Datos sinteticos: cinco filas, cuatro nombres distintos, dos estados activos,
  uno inactivo y dos desconocidos; costo acumulado 1100 con duplicado conservado.
- Conversacion: inactivos 20% de cinco filas, activos 40%; no confundir con
  el 33,3% inactivo sobre tres estados reconocidos en la lectura del catalogo.
- Casos de cero, desconocidos, denominador incoherente, filtros, meses y
  preguntas sobre activos financieros que no corresponden al catalogo.
- Playwright en 390 y 1280 px, numeros largos y una vista UF completa.

Esto no completa la auditoria de CxC, compras con detalle ni rotacion de
inventario del modelo empresarial. Esos pendientes no se ocultan con este cambio.
