# Compras en el bot e invalidacion de resultados antiguos

## Hallazgos reproducidos

- `cuanto compre` se normalizaba como `cuanto compra` y terminaba en una guia
  generica. Con series de ventas presentes, `cuanto compre en enero` podia
  devolver el ingreso de enero. Compras y ventas no comparten esa medida.
- La cache de la pestana conservaba resultados durante 24 horas sin comprobar
  la version del motor. En una sesion existente, incluso despues de recargar,
  Vision del negocio podia mostrar el cero de compras calculado antes de la
  correccion de importes ausentes de la version 0.32.8.

## Cambios

- El bot usa los contratos publicados de `compras_netas` y `fletes_compra`.
  Conserva moneda, estado parcial, cobertura y fuentes. Un importe bloqueado,
  ausente o no finito no se convierte en cero ni se obtiene de las ventas.
- Las preguntas de cantidades, proveedores, promedios, IVA y pagos no se
  contestan con el importe neto. Un alcance no publicado tampoco se sustituye
  por el total general. Las continuaciones conservan el tema y alcance; una
  pregunta nueva sobre ventas, cartera o inventario cambia de tema.
- El vocabulario conserva `compre` y `comprando`, y separa `cuantocompre`.
- La restauracion comunica la version del motor y del modelo derivados que
  ejecuta el servidor. La cache de metricas, relaciones, catalogos y dashboards
  manuales solo reutiliza entradas con esa version. Las entradas antiguas sin
  version se descartan. Reabrir el mismo libro con el mismo motor conserva la
  optimizacion.
- Se mantienen el archivo, las reglas, la limpieza y la decision sobre
  duplicados. Invalidar resultados analiticos no borra documentos ni obliga a
  subirlos otra vez.

## Comprobaciones

- Casos de bot con CLP, UF y USD, cero observado, nulos, bloqueo, cobertura
  parcial, cambios de tema y filtros no publicados.
- Integracion del contrato real del motor de compras con la respuesta del bot.
- Contextos de compras mal formados se rechazan antes de ejecutar el lector;
  los campos opcionales nulos siguen mostrando informacion no disponible.
- Auditoria reproducible de 170 turnos: sin fallos en esos escenarios.
- Pruebas de cache: cambio de motor, cambio de modelo, entradas sin version,
  permanencia del mismo motor y aislamiento ya existente entre sesiones.
- La suite completa detecto una regresion inicial en `comprando`; se agrego
  esa forma al vocabulario y se volvieron a ejecutar los casos afectados.
- Validacion local: 1690 pruebas backend completas aprobadas antes del ultimo
  endurecimiento de estructura; despues, 300 pruebas focalizadas aprobadas.
  Frontend: 227 pruebas, compilacion de produccion y cinco pruebas Playwright
  de cabecera/detalle, reintentos y presentacion desktop/mobile aprobadas.

## Limites

Esto no reconstruye todavia todas las compras de cabecera/detalle ni certifica
la conciliacion completa del libro PYME. El bot solo responde indicadores
publicados. La invalidacion se aplica al restaurar la sesion o abrir desde
Historial; una pagina ya abierta debe recargarse para recibir el nuevo codigo.
No se activa IA de pago, pasarela ni infraestructura contratada.
