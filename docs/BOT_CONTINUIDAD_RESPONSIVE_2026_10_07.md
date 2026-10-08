# Continuidad del asistente y sugerencias del catalogo

## Hallazgo

Al cruzar el ancho de 1280 px, AppShell desmontaba el asistente lateral y
creaba otro dentro del drawer movil. Se perdian el historial, las sugerencias
y el borrador; una respuesta pendiente se cancelaba por el desmontaje.
Cerrar y abrir el mismo drawer ya conservaba la instancia, pero cambiar entre
los dos modos de presentacion no lo hacia.

## Correccion

Una unica instancia ocupa la misma posicion en el arbol de React. Solo cambian
el contenedor y la variante visual entre columna lateral y drawer. En movil,
el panel no se monta antes de abrirse por primera vez. Una vez mostrado,
ocultarlo no borra la conversacion ni vuelve a enviar solicitudes.

No se persiste el historial en disco. Las reglas de reinicio por archivo,
hoja y filtros siguen vigentes, igual que la cancelacion al desmontar la
pantalla. La IA avanzada sigue requiriendo activacion explicita; el bot no
consume ADS Coins. No hay cambios en limpieza, estandarizacion o indicadores.

## Sugerencias segun el contexto

En la hoja de productos publicada, las sugerencias iniciales invitaban a pedir
ingresos aunque la vista era un catalogo. Las sugerencias iniciales y las de
las respuestas ahora preguntan por productos, costo promedio de referencia y
margen potencial. Esto tambien evita que KPI heredados de un contrato anterior
vuelvan a introducir preguntas de ventas en esa vista.

La conversacion de tres preguntas sugeridas descubrio que `margen potencial`
era interceptado como utilidad realizada. Se prioriza el contexto de catalogo,
manteniendo las restricciones de moneda mixta y de periodos o productos sin
desglose publicado. No se convierte un margen de lista en ganancia realizada.

## Validacion local

- Dos regresiones nuevas fallaban antes de la correccion: conservar historial
  y borrador entre escritorio y movil, y terminar una respuesta pendiente al
  pasar de movil a escritorio sin duplicar su solicitud.
- Las cinco pruebas de `frontend/e2e/bot_context.spec.ts` pasan tras el cambio.
  Incluyen historial, nueva conversacion, descarte de respuestas al cambiar
  hoja o periodo, y ajuste de textos largos a 390 px sin desborde horizontal.
- 229 pruebas unitarias del frontend aprobadas, incluidas dos nuevas del catalogo.
- 247 pruebas de auditoria de conversacion del backend aprobadas, incluidas
  siete nuevas para sugerencias, dialogo sugerido, alcances y moneda mixta.
- Compilacion de produccion aprobada.

Los tests usan respuestas y archivos sinteticos. El CI repite la validacion
completa antes del merge. Los resultados no certifican por si solos capacidad
concurrente, exactitud de todos los libros financieros ni viabilidad comercial.
