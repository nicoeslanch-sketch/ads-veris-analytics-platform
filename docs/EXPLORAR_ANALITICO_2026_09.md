# Explorar: lectura analitica fundamentada

La presentacion de seis bloques descrita abajo fue reemplazada el 14 de septiembre por graficos con lectura breve y detalles plegados. Ver [la actualizacion](ESCALADO_Y_SEGURIDAD_2026_09_14.md).

## Cambio de experiencia

Explorar deja de reutilizar los paneles de Resumen. Presenta una lectura propia
con seis bloques: cifra y definicion, diferencias observadas, limites de la
conclusion, conexiones entre hojas, siguiente comprobacion y evidencia numerica
desplegable. No depende de un modelo generativo ni realiza llamadas nuevas para
redactar el texto: usa las metricas del motor y la cache existente.

Se conservan seleccion de hoja, periodo, medida, dimension, filtros empresariales,
guardado de analisis y ajuste manual de relaciones. El asistente global sigue
disponible; se retira la recomendacion generativa separada de esta pagina.

## Guardas analiticas

- Compara meses consecutivos completos; excluye meses parciales y bordes de un
  filtro que no cubran el mes. No calcula crecimiento sobre bases cero o negativas.
- Descompone cambios por grupo solo cuando el cruce mensual concilia con los dos
  totales. Explica aportes al cambio, no causas demostradas.
- Informa cuando un ranking esta recortado. Valores negativos no se convierten en
  participaciones positivas ni en conclusiones de concentracion.
- Gastos, neto e IVA permanecen separados. El inventario cuenta registros bajo
  minimo, no productos unicos. Catalogos describen referencias, no ventas.
- Cobranza distingue el monto cobrado del total nominal y no mezcla sus grupos.
  Marketing no infiere ROAS sin ingresos atribuidos. Servicios separa resultados
  brutos y operacionales.
- Expone duplicados conservados, fechas invalidas, cobertura de costos,
  correspondencias, claves ausentes y controles de formula cuando estan disponibles.
- No suplanta utilidad o liquidez desconocidas por cero ni por otra base de KPI.
- Mientras cambia el filtro no muestra cifras antiguas bajo la nueva seleccion.
  La demo congelada conserva todo su periodo y no modifica el periodo real.

## Verificacion

- Pruebas deterministas: `frontend/src/lib/explorationAnalysis.test.ts`.
- Recorrido visual aislado: `frontend/e2e/exploration_narrative.spec.ts`, escritorio
  1440 px y movil 390 px, seleccion de medidas/desgloses, evidencia, ausencia de
  desborde y errores de pagina. Primera ejecucion aprobada; capturas revisadas.
- TypeScript y compilacion de produccion aprobados durante la implementacion.

La interpretacion sigue dependiendo del mapeo, grano y datos entregados al motor.
Una union por ID no demuestra causalidad; una alta completitud tampoco garantiza
que todos los importes o fechas sean correctos. Las comprobaciones propuestas
son preguntas de auditoria, no resultados financieros inventados.
