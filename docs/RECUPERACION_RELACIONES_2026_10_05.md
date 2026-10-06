# Recuperacion de la validacion entre hojas

## Problema observado

Una interrupcion de comunicacion en `Visión del negocio` podia aparecer como
`No existen conexiones seguras entre las hojas`. Una solicitud fallida no
demuestra que las claves o relaciones del archivo sean invalidas.

En el inicio automatico, un rechazo rapido tambien podia devolver el selector
a `Analizar una hoja`: el efecto de montaje restauraba el alcance anterior
antes de que hubiera un resultado de validacion. La prueba de navegador
reproduce este caso con React StrictMode.

## Correccion

- Estados distintos para revision pendiente, respuesta validada y error.
- Resumen y Explorar no presentan un error operativo como un diagnostico del
  Excel ni muestran el resultado anterior como validacion de la nueva seleccion.
- `Reintentar conexiones` conserva las hojas elegidas y solo vuelve a pedir la
  revision de relaciones; no modifica filas ni borra archivos.
- Las respuestas terminadas siguen siendo reutilizables. Un fallo no se guarda
  en la cache como una respuesta vacia.
- Mientras esta revision esta en curso o ha fallado, las paginas no inician
  nuevas solicitudes de metricas para el alcance anterior. Un trabajo compartido
  que ya estaba en curso conserva el comportamiento de la cache existente.
- La seleccion iniciada automaticamente permanece visible tras un fallo rapido.

## Regresiones

Pruebas de navegador con un libro sintetico cabecera-detalle, dos periodos,
catalogos y cartera: interrupcion de red en Resumen, rechazo 429 en Explorar,
reintento con el mismo foco y resultado financiero real del motor. Otro caso
comprueba que una respuesta correcta sin candidatos si muestra la ausencia de
conexiones validadas. Se comprueba tambien el ancho movil de 320 px.

Las pruebas existentes mantienen los importes con catalogo normal y repetido.
La prueba unitaria de cache comprueba rechazo, reintento y reutilizacion.

Esto corrige la recuperacion y el mensaje de interfaz. No establece la causa
del corte observado en produccion, no elimina todas las posibles caidas del
servidor y no certifica capacidad simultanea ni latencia comercial.
