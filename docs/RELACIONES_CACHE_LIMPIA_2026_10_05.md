# Reutilizacion de tablas limpias en relaciones

## Evidencia inicial

Una solicitud real de `/sheets/relationships` del caso PYME termino con HTTP
200, pero Render registro 109.349 ms de duracion. No se hizo una prueba de
carga ni se atribuye toda esa duracion a una sola causa.

El lector comun de manifiestos ya admite tablas limpias persistidas y firmadas.
Las metricas le pasaban el usuario autenticado; las tres entradas de relaciones
no lo hacian, por lo que no podian leer ni guardar esa reutilizacion durable.

## Cambio

- Vision del negocio, catalogo de conexiones y dashboard de relacion pasan el
  ID del usuario autenticado hasta el lector comun del manifiesto.
- La identidad de una tabla limpia incluye explicitamente al usuario, ademas
  del archivo, dataset, hoja, revision, reglas, mapeo y version del motor.
- Se mantienen la firma, el prefijo privado por usuario, los limites de celdas
  y la verificacion de identidad. No se agregan permisos ni buckets publicos.
- Un objeto ajeno copiado a otro prefijo tampoco pasa la identidad esperada.
- Si falta un artefacto, su identidad no coincide o su firma no es valida, se
  utiliza el procesamiento normal. No se aceptan resultados antiguos.

No se modifican reglas de limpieza, exportaciones, filas, moneda, joins ni
formulas. Los artefactos anteriores a este cambio se reconstruyen una vez;
no se borran archivos originales ni la configuracion de limpieza del usuario.

## Pruebas

Las pruebas aisladas usan almacenamiento en memoria y un Excel sintetico:

1. Crear tablas limpias persistidas de dos hojas.
2. Vaciar las caches en memoria.
3. Recuperarlas mediante cada una de las tres entradas de relaciones.
4. Fallar la prueba si se vuelve a abrir el XLSX o ejecutar la limpieza.
5. Comparar los DataFrames recuperados con los originales.
6. Comprobar aislamiento tanto con memoria caliente como con un objeto firmado
   colocado equivocadamente en el prefijo de otro usuario.

Las regresiones existentes mantienen la invalidacion por revision y las
comprobaciones de cardinalidad, documentos, monedas y calculos de relaciones.

La mejora reduce calculos repetidos cuando las tablas ya estan disponibles.
La primera generacion de un archivo/version nueva y la latencia de Storage
siguen teniendo costo. No se promete una latencia concreta en Render ni una
capacidad comercial de usuarios por estas pruebas.

Referencia de control de acceso: [Supabase Storage](https://supabase.com/docs/guides/storage/security/access-control).
