# Cache multioja y errores de objetos ausentes

## Evidencia

Al verificar la publicacion anterior, el primer analisis empresarial termino,
pero la espera siguio superando un minuto. La inspeccion acotada de los logs
del proveedor identifico nueve lecturas internas con HTTP 400, codigo
`NoSuchKey` y estado interno 404. No eran errores de autorizacion ni evidencia
de caida de Storage: esos objetos derivados aun no existian.

Ademas, la cache de tablas limpias conservaba una sola hoja. Recorrer varias
hojas expulsaba las anteriores y repetia sus descargas al construir otra vista.
Cinco de seis regresiones nuevas fallaron antes de corregir este comportamiento.

## Cambios

- Solo en artefactos internos opcionales se reconoce el objeto ausente dentro
  de HTTP 400: `code=NoSuchKey` o el formato heredado `statusCode=404` junto con
  `error=not_found`. No basta un mensaje de texto que diga "not found".
- El cuerpo de error se inspecciona con un maximo de 8 KiB. JSON invalido,
  demasiado profundo o excesivo no se acepta como cache ausente. Los errores
  de permisos, servicio, cuotas y bucket siguen siendo errores.
- Las descargas de archivos originales siguen siendo obligatorias; no se
  convierten en lecturas opcionales. No se cambian RLS, permisos ni firmas.
- La cache en memoria conserva hasta 32 hojas dentro de un presupuesto TOTAL
  de 600.000 celdas, igual al limite anterior de una unica hoja. Las hojas
  menos utilizadas se expulsan primero. Las entradas grandes se omiten.
- Se conservan las claves de identidad por usuario, dataset, revision,
  contenido, reglas, alcance y version. Las vistas reciben copias de las
  tablas, sin alterar el contenido conservado.

Referencia del proveedor:
https://supabase.com/docs/guides/storage/debugging/error-codes

## Verificacion y limites

57 pruebas focalizadas y 1.732 pruebas backend completas aprobadas: lectura de objetos, formatos de error,
limites de memoria por celdas, eviction LRU, revisita sin red ni limpieza,
firmas y aislamiento entre usuarios. CI vuelve a ejecutar los controles antes
de fusionar la revision. La ejecucion local conserva 30 avisos de deprecacion
preexistentes; no son fallos de las pruebas.

El presupuesto por celdas no es una garantia exacta de RSS: textos, indices y
metadatos tienen costos adicionales. No se incrementa el limite de trabajos
pesados ni se certifican usuarios simultaneos. Una instancia nueva o un libro
sin artefactos compatibles todavia requiere trabajo inicial. Este cambio no
demuestra una reduccion concreta de segundos en produccion hasta medirla.

No se modifican originales, reglas de limpieza, duplicados, calculos ni planes.
