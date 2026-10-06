# Importes de compras y fletes: ausencia no equivale a cero

## Fallo reproducido

La suma de una serie vacia, sin columna monetaria o con todos los importes
invalidos producia `0.0`. El catalogo de indicadores la etiquetaba como
disponible. Una suma parcial tampoco declaraba su cobertura.

Se reprodujo con pruebas sinteticas antes de cambiar el motor: 10 de las 11
primeras comprobaciones fallaron, incluyendo el importe neto y los fletes.

## Correccion

- Sin importes validos en el alcance: valor `None`, estado no disponible y
  advertencia. No se inventa un cero ni se toma un total global para un filtro.
- Un importe cero realmente presente sigue siendo cero disponible.
- Sumas con valores faltantes: estado parcial, cobertura y advertencia incluso
  cuando la cobertura supera el 99,5 %.
- Los fletes usan una contribucion por ID de compra. La cobertura cuenta
  documentos, no lineas repetidas. Los IDs conservan sus ceros iniciales.
- Fletes contradictorios para un mismo documento bloquean el total. No se
  escoge arbitrariamente la primera fila. Filas sin ID no certifican un flete
  por documento y reducen la cobertura del subtotal conocido.
- Los archivos originales y la limpieza guardada no se modifican.

El motor pasa a `0.32.8` para que un resultado previo de cero supuesto no se
reutilice desde las caches y snapshots del motor anterior.

## Validacion y alcance

`api/tests/test_purchase_indicators.py` cubre columna ausente, valores nulos o
ilegibles, suma parcial, cero observado, periodo sin importe elegible, filtro
por producto, fletes vacios, repeticiones, conflictos, IDs ausentes y ceros
iniciales. Se ejecuta junto con las regresiones de negocio, documentos y cache.

Esta correccion no reconstruye un modelo general de compras cabecera-detalle,
ni consolida automaticamente todas las hojas de compra. Ese trabajo requiere
una validacion independiente de grano, claves, impuestos, descuentos y fechas.
Por tanto, no certifica todavia todos los KPIs de compras del caso PYME.

## Conversacion en produccion

La prueba en el navegador tambien descubrio un fallo de continuidad: al
concatenar mensajes para buscar un segmento, `me deben` seguido de
`y las vencidas` producia una falsa referencia a un deudor llamado `y`.
El bot ahora valida los alcances dentro de cada mensaje, manteniendo las
restricciones de un cliente o periodo real, sin unir palabras entre turnos.
La secuencia exacta y las variantes con `nos deben` tienen regresiones.
