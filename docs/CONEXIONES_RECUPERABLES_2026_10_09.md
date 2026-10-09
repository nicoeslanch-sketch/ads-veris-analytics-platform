# Conexiones recuperables

## Hallazgo

La vista Vision del negocio y la validacion manual aun usaban
`POST /sheets/relationships`: una conexion HTTP permanecia abierta durante
todo el calculo. En una prueba de produccion se observo un fallo de comunicacion;
el reintento termino con HTTP 200 en 76,9 segundos. Render no registro reinicios
ni agotamiento de memoria en esa ventana. No se ha establecido la causa exacta
de la interrupcion inicial.

## Cambio

- Ambas vistas utilizan `POST /analysis/jobs/relationships` y el sondeo existente.
- La fuente guardada se encola por referencia, con propietario, dataset, version
  y opciones en la identidad. No se carga el Excel en la peticion de admision.
- El worker reutiliza `_relationships_cached_sync`: mismas reglas de limpieza,
  correspondencias, cardinalidad, costos y deteccion de catalogos ambiguos.
- Se rechazan hojas no seleccionadas y alcances ambiguos antes de encolar.
- La cola conserva limites, permisos, cancelacion, reintentos y fencing.
- El endpoint sincronico se conserva para compatibilidad.
- La version 0.32.9 evita que workers anteriores reclamen la nueva operacion.
  La migracion solo amplia los tipos admitidos por la cola privada; no cambia
  acceso a tablas, RLS ni datos de clientes.

## Verificacion

- Pruebas backend de admision sin descargar el archivo, permiso de plan,
  seleccion de hojas, opciones y despacho del mismo motor.
- Prueba SQL aislada: admision, idempotencia, aislamiento de lectura/cancelacion/
  reintento entre propietarios y recuperacion del resultado terminado.
- Navegador: corte simulado HTTP 503 durante el sondeo, sin duplicar trabajos;
  se verifican ventas, costo, utilidad y CxC de un libro sintetico, tanto con
  catalogo unico como con claves repetidas. Se revisa el ancho a 1280/390/320 px.

## Limites

Esto mejora la continuidad, no promete reducir el tiempo del motor. Una medicion
de filtro en produccion antes de este cambio registro 38,44 s de ejecucion:
37,46 s de calculo y 0,10 s de preparacion de las 18 hojas limpias. Los tiempos
de etapas son inclusivos y no deben sumarse. Son una muestra de un archivo,
no una certificacion de concurrencia ni una comparacion antes/despues.

El sondeo mantiene el presupuesto existente de cuatro minutos; una interrupcion
prolongada, una cuota agotada o un error del motor siguen siendo errores explicitos.
Los pagos y la IA avanzada permanecen desactivados. No se contrataron servicios.
