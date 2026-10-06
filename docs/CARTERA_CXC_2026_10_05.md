# Cartera por documentos y saldos

## Contrato del calculo

- CxC con saldo e identidad explicita se reconoce como cartera, no como
  ventas, pagos, ni una maestra de clientes.
- El saldo declarado y el validado son distintos. El primero conserva el
  importe original de las filas; el segundo usa cuentas con IDs vinculados
  a ventas validas, saldo finito no negativo y estado coherente.
- Los IDs solo se recortan y comparan sin distinguir mayusculas. No se
  eliminan ceros iniciales ni se usan coincidencias aproximadas.
- Una cuenta puede tener varias cuotas identificadas. Las lineas de venta
  se reducen a un conjunto de documentos para verificar pertenencia, nunca
  se unen a los saldos en una tabla que multiplique los importes.
- Las copias analiticas identicas cuentan una vez y se informan. Todas las
  filas fisicas del Excel y sus duplicados siguen en la limpieza/exportacion.
  Las identidades contradictorias no eligen arbitrariamente la primera fila.
- Saldo negativo, superior al original, original invalido, cuenta pagada con
  saldo abierto, cuenta anulada y documento sin venta valida se controlan
  por separado. Un universo completamente invalido no se presenta como cero.
- Un saldo sin fecha de corte se etiqueta como declarado sin corte. No se
  reconstruye cartera historica filtrando la fecha de emision, ni se usa el
  saldo global como respuesta a un filtro por producto, sucursal o cliente.
- Con cortes explicitos se toma el ultimo no posterior al limite solicitado,
  no se suman meses. La fecha inicial del filtro no elimina deuda antigua.
  Una emision posterior al corte queda fuera de la cartera validada.
- Mora requiere fecha de vencimiento y corte, o estado vencido explicito.
  Los faltantes quedan visibles y la cartera vencida parcial no se certifica
  como completa. El saldo no inventa una fecha de corte usando la fecha actual.
- Monedas incompatibles bloquean el saldo. No se renombran UF como CLP ni
  se convierten sin tipo de cambio declarado.

## Verificacion

`api/tests/test_receivables_ledger.py` usa unicamente datos sinteticos para
probar estos limites y la integracion cabecera-detalle-cartera.

`frontend/e2e/document-model.spec.ts` incluye cuentas validas, un saldo negativo,
una cuenta pagada con saldo y una venta anulada. Comprueba el saldo resultante,
la conservacion de las ventas y el ajuste visual a 1280, 390 y 320 pixeles.

`scripts/audit_pyme_control.py` calcula la cartera desde el archivo original
con Decimal, independientemente del motor, y contrasta importe, cantidad y
controles con el resultado local de la plataforma. Los archivos y resultados
de usuario permanecen fuera del repositorio publico en `artifacts/`.

## Limites

Esta entrega no reconstruye movimientos de caja, DSO financiero aproximado ni
cartera por segmentos sin evidencia suficiente. No da por terminado el
contraste de todos los KPIs del control: compras cabecera-detalle y rotacion
de inventario siguen pendientes. Tampoco sustituye un ensayo de recuperacion
de produccion ni certifica capacidad comercial del servidor de Render.

Motor 0.32.7 invalida las caches analiticas previas. No cambia esquemas de la
base de datos, precios, planes, proveedor de IA ni habilita cobros reales.
