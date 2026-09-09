# Auditoria multihoja: motor 0.30.0

Fecha: 8 de septiembre de 2026. Esta revision complementa las auditorias
anteriores; no reutiliza sus cifras ni presupone que se eliminaron duplicados.

## Fallos corregidos

- La limpieza por lote permanecia en una peticion HTTP durante el calculo de
  todas las metricas y su guardado. El navegador podia declarar error aunque
  el servidor terminara mas tarde. Estandarizacion y limpieza ahora usan
  trabajos consultables, con progreso por hoja y fase de guardado.
- El guardado de seleccion podia competir con la revision del procesamiento.
  Ahora se espera el guardado pendiente y se bloquean cambios de seleccion
  mientras se procesa el lote.
- Los snapshots limpios pueden guardar metricas pendientes explicitamente.
  Abrir Resumen calcula las metricas necesarias; descargar conserva las mismas
  reglas de limpieza y no depende de que se haya abierto cada dashboard.
- Pandas copiaba la lista completa de filas de origen en operaciones temporales.
  La limpieza separa esa metadata y la repone al terminar; el analisis empresarial
  usa procedencia inmutable. Las filas originales siguen siendo trazables.
- Los trabajos terminados liberan la funcion que retenia el archivo cargado.
  La cola tiene un limite y nunca descarta trabajos activos para hacer espacio.
- La comprobacion en produccion detecto que la URL firmada de exportacion usaba
  una ruta relativa de Storage sin el prefijo /storage/v1. El XLSX quedaba guardado
  pero la redireccion fallaba. Se corrige la ruta y se prueban las tres variantes
  de URL: relativa al API, relativa al proyecto y absoluta.
- Gastos con encabezados explicitos, incluso en tablas pequenas, no se presentan
  como ventas. Las metas constantes siguen apareciendo como indicadores.
- Los perfiles operacionales no conservan graficos comerciales residuales.
  Fechas, IVA y montos numericos no se convierten en categorias por tener pocas
  observaciones. Los desgloses operacionales separan totales y promedios.
- Los graficos con importes negativos usan barras, sin tortas, Pareto ni
  porcentajes de concentracion calculados sobre un neto enganoso.
- El nombre del alcance individual cambia junto con la hoja activa. Los modos
  de relacion y consolidacion mantienen su seleccion explicita.
- Una deteccion de relaciones que termina tarde ya no reemplaza la hoja elegida
  manualmente. Esa decision se conserva al navegar entre Resumen y Explorar.
- Leyendas largas se distribuyen en HTML ajustable; tarjetas y valores tienen
  restricciones de ancho. Clics y CTR usan ejes distintos.
- Una pestana abierta antes de un despliegue podia pedir un modulo que ya no
  existia y quedar en blanco. El limite de errores de cada vista mantiene la
  navegacion y el dataset activo, y ofrece recargar sin borrar la seleccion.

## Evidencia de datos

El libro desafiante contiene 16 hojas. La hoja Parametros tiene 6 registros;
las otras 15 contienen 27.068 filas tabulares. La carga distingue esos registros
de las filas de presentacion del archivo fisico.

Se verificaron 137 repeticiones exactas sobre los datos originales. Se conservaron
todas: esta auditoria no autoriza eliminarlas. Tras normalizar formatos hay 174
filas repetidas en la exportacion, incluyendo 37 coincidencias adicionales en las
hojas de ventas. No es una perdida de filas ni una autorizacion para borrar esas
coincidencias.

Las 15 hojas exportadas conservan sus conteos y encabezados. El XLSX se genero
con el exportador real y se volvio a abrir con un lector independiente. Las
sumas de ventas de los tres periodos coinciden con los KPI, aplicando las reglas
explicitas de exclusion de anulaciones y filas TOTAL, conservando devoluciones,
nulos identificados y duplicados no eliminados.

La comprobacion en produccion repitio la limpieza de las 15 hojas sin errores
ni eliminaciones. El archivo descargado del sitio se abrio con openpyxl:
contiene las 16 hojas de origen y las hojas Observaciones, Auditoria y
Manifest. Sus conteos, 174 repeticiones normalizadas y sumas de ventas
coinciden con la referencia independiente. La descarga se verifico despues
de corregir la ruta de Storage, no solo con un exportador local.

La limpieza optimizada reproduce los informes anteriores para las 16 hojas y
conserva la procedencia de cada fila. Bajo el mismo perfilador, la limpieza de
una hoja de 4.057 registros bajo de 7,683 a 3,106 segundos. No es una promesa de
latencia en Render: red, cache, concurrencia y capacidad del servicio influyen.

## Bot

Se revisaron 45 intercambios encadenados con metricas reales de cinco perfiles:
ventas, inventario, gastos, metas y clientes. Se agregaron regresiones para
palabras unidas, errores de escritura, maximo/mediana en seguimientos,
distincion de neto/IVA/total, conteo de clientes y stock por sucursal.

El diccionario combina vocabulario protegido, alias y segmentacion; no intenta
enumerar todos los errores posibles ni modificar identificadores del archivo.
Las respuestas financieras siguen usando la biblioteca existente y solo afirman
cifras presentes en las metricas. Ventas no demuestra utilidad, inventario no es
caja y una meta no es ingreso realizado.

Una conversacion adicional de 15 preguntas en la interfaz de produccion cubrio
ventas, ganancia, clientes unicos, meses extremos, duplicados, UF, relaciones,
gastos, IVA, neto, maximos, categorias, liquidez y descarga. Revelo una confusion
entre preguntas sobre el mes con mas ventas y ayuda de fechas, ahora cubierta
por regresiones tambien con palabras unidas. Las sugerencias iniciales cambian
segun el perfil; una hoja de gastos no ofrece ingresos como primera pregunta.
Si faltan fuentes para liquidez, el bot indica que necesita activos y pasivos
corrientes de la misma fecha, sin inventar el indicador.

## Reproduccion

Verificacion previa a publicacion: 798 pruebas de backend, 145 pruebas unitarias
de frontend y 16 recorridos de navegador aprobados. El recorrido del libro real
reconcilia los KPI de ventas con la exportacion independiente y verifica los
desgloses operacionales en escritorio y movil. Compilacion de produccion y
control de dependencias tambien completados.

```powershell
python scripts/audit_challenging_workbook.py <archivo.xlsx> --output tmp/audit.json --metrics --export tmp/audit-export.xlsx
cd api
python -m pytest -q
cd ../frontend
npm test
npm run build
npm run audit:ci
npm run test:e2e -- --workers=1
```

El recorrido opcional del archivo desafiante usa ADS_AUDIT_WORKBOOK y
ADS_AUDIT_REFERENCE (el JSON revisado). Los archivos fuente, exportaciones,
conversaciones y capturas permanecen fuera del repositorio.

## Limites

Esta auditoria cubre regresiones automatizadas de carga, tipos, formulas,
monedas, exportacion, relaciones, permisos y conversaciones, ademas del libro
proporcionado. No certifica cualquier archivo imaginable ni reemplaza una
auditoria contable de origen. Valores ambiguos, claves conflictivas, referencias
huerfanas y formulas no soportadas deben permanecer visibles, no inventarse.

La ejecucion pesada sigue siendo secuencial para cuidar la memoria de la
instancia gratuita. Los trabajos sobreviven a una desconexion del navegador,
pero un reinicio del proceso puede requerir reintentar lo no guardado. No se
ha contratado infraestructura adicional ni se promete procesamiento instantaneo.
