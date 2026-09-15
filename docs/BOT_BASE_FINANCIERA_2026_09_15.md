# Coherencia financiera del bot

## Hallazgo

Al probar una conversacion real en Explorar, la pregunta por ingresos coincidia
con el grafico, pero la pregunta siguiente sobre utilidad usaba los KPI genericos.
Esos KPI no tienen necesariamente las mismas exclusiones, filtros ni cobertura
de costos que `analisis_negocio.estado_resultados`. La respuesta podia contradecir
la medida visible y cambiar incluso el signo del resultado.

## Correccion

Las preguntas financieras globales sobre una Vision del negocio ahora leen su
estado de resultados publicado, sin recalcular ni modificar la limpieza:

- Ingresos: `ventas_observadas`.
- Costo de venta conocido: `costo_venta_conocido`.
- Gastos operacionales: `gastos_operacionales`, separados del costo de venta.
- Utilidad bruta y margen: la base pareada del modelo empresarial.
- Resultado operacional y cifras certificables: sus campos especificos.
- Cobertura: la misma base empresarial; no el porcentaje generico.

Los valores ausentes siguen ausentes, cero sigue siendo cero y las perdidas
conservan su signo. No hay conversion automatica entre UF y CLP. No se publica
una utilidad neta ni caja disponible a partir de utilidad bruta. Los pedidos de
desgloses no se responden sustituyendolos por el total global.

Las consultas de cobranza mantienen su lector propio y las hojas sin modelo
empresarial conservan sus KPI. Esta correccion no amplifica los permisos del bot
ni le permite consultar otras cuentas.

## Pruebas

`test_assistant_business_finances.py` usa deliberadamente KPI genericos y
empresariales contradictorios. Cubre 24 casos, incluyendo conversaciones,
palabras unidas, moneda UF, filtros, nulos, cero, perdidas, monedas incompatibles,
desgloses solicitados y validacion de la estructura recibida.
La suite completa del backend termino con 1.118 pruebas aprobadas.

Se incorporaron `operacional` y `operacionales` al vocabulario para evitar que
se separasen incorrectamente como palabras distintas.

La prueba de liberacion de usuarios expirados del limitador usa un reloj
monotonico simulado. Antes dependia de que la maquina llevara mas de un minuto
encendida; el cambio es solo de prueba, no reduce el limite de peticiones.
