# Duplicados en la conversacion y medicion de filtros

## Hallazgos y correcciones

- Una pregunta sobre el efecto de los duplicados repetia el diagnostico general
  de calidad. Algunas variantes con filas repetidas o compras podian devolver
  el importe actual, que no es un total corregido.
- El bot distingue ahora impacto, revision y peticion de borrado. No resta un
  numero de filas a un importe ni promete que eliminar siempre reduce ventas:
  el signo, los filtros y la pertenencia al indicador importan.
- Las preguntas de duplicados por periodo o segmento no reutilizan el conteo
  general ni la serie de ventas. Los seguimientos conservan el tema dentro del
  historial limitado, y una pregunta nueva de ventas cambia el tema.
- Se conserva un cero publicado explicitamente. Un conteo ausente, negativo,
  fraccionario, booleano o no finito no se convierte en cero.
- El chat no elimina filas. La revision distingue repeticiones exactas,
  conflictos de ID y lineas legitimas de un mismo documento.
- El vocabulario cubre nuevas formas de preguntas y palabras juntas. Las
  pruebas detectaron que agregar `conviene` alteraba `convierte`; se preserva
  explicitamente la segunda forma para no perder la cautela sobre monedas.

## Evidencia reproducible

- Regresiones con datos sinteticos, CLP, UF, USD, valores ausentes, cero,
  alcances no publicados, pedidos de borrado y cambios de tema.
- Conversacion de 12 turnos agregada a `scripts/exercise_assistant.py` mediante
  el catalogo compartido de escenarios. No incluye datos de clientes.
- Se mantienen los controles anteriores para cobranza sin identificador unico
  de pago y la separacion entre compras, ventas, utilidad y caja.
- Validacion local: 1779 pruebas completas aprobadas antes de los ultimos
  ajustes de vocabulario y dos casos adicionales; despues, 350 pruebas
  focalizadas y 182 turnos de conversacion aprobados. El CI vuelve a ejecutar
  la suite completa sobre el commit final.

## Medicion en produccion de la version anterior inmediata

Con `f0270377db908c7edb48b0528cf913bfd1cf2625` (PR 64), en una sesion real de
un libro de 18 hojas, sin carga concurrente generada por esta prueba:

- Primer filtro: seguia calculando a los 30 s; completado al observar a los 60 s.
- Segundo filtro distinto: seguia calculando a los 46 s; completado al observar
  a los 68 s, aun despues de cargar las hojas con el primer filtro.
- Volver a la vista general ya calculada mostro el mismo total en la accion de
  seleccion (menos de un segundo observado).

Son intervalos observados desde la interfaz, no duraciones exactas ni percentiles.
No demuestran causalidad ni certifican capacidad comercial. La cache reduce
trabajo repetido, pero los filtros nuevos siguen necesitando optimizacion del
calculo. No se realizaron pruebas de saturacion sobre produccion.

## Limites

No cambia el motor de limpieza ni calcula un escenario financiero sin duplicados.
La conciliacion completa contra el libro de control y la capacidad comercial
representativa siguen pendientes. No se activa IA de pago, cobros ni servicios
contratados. Las evidencias privadas permanecen fuera del repositorio.
