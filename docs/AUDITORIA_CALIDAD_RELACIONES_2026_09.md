# Calidad de datos y relaciones entre hojas

Revision local de septiembre de 2026, complementaria a
`AUDITORIA_MULTIHOJA_2026_09.md`. No se subieron archivos adicionales ni se
modifico el libro original. Las cifras de esta revision proceden del libro
`Prueba_PYME_Desafiante_Multihoja_ADS_VerIs_2026.xlsx` ya proporcionado.

## Alcance y criterio

La unidad de analisis es una fila de la hoja fuente. Estandarizar formatos
no autoriza borrar registros, rellenar importes faltantes ni inventar claves.
Las relaciones deben preservar el grano de ventas y demostrar la cobertura
de sus claves. Los costos historicos necesitan ademas una fecha de vigencia
valida para la fecha de cada venta.

Se revisaron encabezados, identificadores, fechas imposibles, importes UF,
duplicados originales, procedencia, claves compuestas, orfandad, multiplicacion
por joins, moneda de costos, versiones historicas y controles de formulas.
El script existente ejecuto de nuevo la carga, estandarizacion, limpieza,
metricas y analisis empresarial del libro real. La exportacion no se repitio:
su conciliacion independiente esta documentada en la auditoria anterior.

## Hallazgos corregidos

| Hallazgo | Riesgo y evidencia | Correccion |
| --- | --- | --- |
| Alto: encabezados con sufijos | `Monto, Monto, Monto_2` producia dos columnas `Monto_2`. La seleccion por nombre podia fallar o ser ambigua. | Se reservan todos los nombres existentes antes de asignar sufijos; nombres unicos e idempotentes, sin modificar celdas. |
| Alto: nombre usado como clave | Vision del negocio elegia el rol de presentacion `Producto` antes que `SKU_Producto`. El libro real daba 0% de cobertura con productos y costos. | Los cruces y filtros empresariales priorizan ID/SKU cuando existe; los nombres siguen siendo etiquetas de presentacion. |
| Alto: costo antiguo despues de una version conflictiva | Enero=10, febrero=20 y febrero=30 dejaban una venta de marzo con costo historico 10 al descartar las filas conflictivas. | La version conflictiva conserva una barrera temporal sin valor utilizable. Un respaldo actual solo puede aparecer como estimacion. |
| Alto: vigencia final ignorada | Un costo con `Fecha_Hasta` podia propagarse a ventas posteriores. | Se respeta el fin inclusivo, se rechazan intervalos invertidos y fechas finales invalidas. Un fin fisicamente vacio sigue siendo abierto. |
| Alto: moneda omitida en estrategia temporal | El dashboard historico retornaba antes de la comprobacion UF/CLP. | La compatibilidad monetaria se verifica antes de ejecutar cualquier estrategia de costos. El catalogo consolidado aplica la misma regla. |
| Medio: relacion historica anunciada sin cobertura temporal | Coincidir por SKU no demuestra que exista costo vigente para la venta. | El catalogo mide coincidencias reales por ID y fecha y exige la cobertura minima existente del motor, 60%. |
| Medio: historial confundido con tarifas | La estrategia `vigencia_por_fecha` del historial entraba al dashboard de tecnicos y devolvia un error de columnas faltantes. | Cada estrategia temporal se despacha segun su dominio. Las ventas con un solo periodo tambien admiten historial valido. |
| Medio: falso control de neto de compras | El control omitia `Flete Total`: marcaba 2.202 inconsistencias en 2.206 filas evaluables. | El neto esperado incluye el flete explicito despues del descuento. Quedan 37 inconsistencias para revisar, sin sobrescribir el dato. |

Confianza alta en los defectos anteriores: cada uno tiene una reproduccion
determinista y una regresion automatizada. La correccion de controles de compras
usa la convencion explicitada por las columnas del libro: cantidad por costo
unitario, menos descuento, mas flete. Otros contratos comerciales pueden usar
una definicion distinta; el control es un aviso, no una correccion automatica.

## Evidencia del libro real

- Las 16 hojas conservan las filas y su procedencia. Son 27.068 registros en
  las 15 hojas de datos y 6 registros adicionales en Parametros.
- Los 137 duplicados exactos originales permanecen. Los 16 informes de limpieza
  coinciden completamente con la referencia independiente anterior. Estos
  cambios no eliminan duplicados ni cambian la exportacion por decision implicita.
- Ventas hacia Productos y Costos reconoce 12.098 de 12.165 filas revisadas:
  99,4% de cobertura, 31 claves huerfanas y 36 filas sin clave. Antes se
  comparaban nombres contra SKU y se anunciaba incorrectamente 0%.
- Los nombres de 85 filas no coinciden con el maestro aunque el ID si existe.
  Esta discrepancia no debe resolverse inventando otro ID.
- Ventas hacia Clientes conserva 30 claves huerfanas y 48 filas sin clave.
  Compras hacia Productos identifica 12 huerfanas; Compras hacia Proveedores,
  16. Cobranzas hacia Ventas identifica 20 huerfanas.
- La cobertura monetaria de costos historicos es 65,8%. Al usar el catalogo
  actual como estimacion se alcanza 98,0%; no son dos cifras intercambiables.
  El historial y los costos estimados tienen procedencia separada.
- Los costos historicos validos no se multiplican por la cantidad de versiones.
  Las ventas sin costo certificado permanecen en ingresos y se excluyen del
  margen pareado, con la cobertura correspondiente visible.
- El control de neto de compras baja de 2.202 a 37 avisos sobre las mismas
  2.206 filas evaluables al incluir el flete. No se cambio ningun monto fuente.

Las distintas coberturas usan denominadores distintos: la integridad de claves
incluye registros que pueden quedar fuera del KPI por estado o fecha; el
porcentaje monetario se calcula sobre ingresos. No deben sumarse ni confundirse
los conteos de diagnostico con el numero de ventas certificadas.

## Pruebas y reproduccion

La nueva suite `api/tests/test_quality_relationship_audit_2026.py` contiene
29 casos adversariales. Junto con las suites existentes de negocio y dashboards
de relaciones pasaron 91 pruebas. Otras 254 pruebas de estandarizacion,
limpieza, exportacion y multihoja tambien pasaron durante esta revision.
Las advertencias obtenidas son de deprecacion, no fallos de asercion.

```powershell
cd api
python -m pytest tests/test_quality_relationship_audit_2026.py tests/test_business_analysis.py tests/test_phase20_relationships.py -q
```

El recorrido reproducible ya existente acepta un archivo local explicitamente:

```powershell
python scripts/audit_challenging_workbook.py <archivo.xlsx> --output tmp/audit-quality-followup.json --compare tmp/audit-verified.json --metrics
```

Los JSON con datos, ejemplos y conversaciones se conservan fuera del control de
versiones. Esta revision cambia resultados analiticos en relaciones e historiales;
la integracion debe incrementar `ENGINE_VERSION` para invalidar caches anteriores.

## Limites y comparacion con Power Query

La plataforma aplica transformaciones automaticas y auditables para los casos
probados; no implementa todo el lenguaje M, sus conectores ni las decisiones
configurables de Power Query. No existe evidencia para afirmar equivalencia
universal ni que cualquier Excel quedara contablemente correcto con un clic.

Se deben seguir revisando fuentes con fechas regionales ambiguas, IDs sin
semantica declarada, monedas mezcladas, tasas implicitas, formulas no soportadas,
maestros conflictivos y referencias incompletas. Los codigos con relleno de ceros
pueden normalizarse para buscar correspondencias; si eso crea una colision en el
maestro, la relacion queda bloqueada. Los identificadores y celdas originales
no se reescriben por esa comparacion.

Una union segura evita multiplicar filas, pero no demuestra causalidad ni que
el maestro sea verdadero. El costo actual de catalogo es una estimacion historica,
los margenes con cobertura parcial no representan todo el negocio y la presencia
de ingresos no demuestra liquidez o utilidad neta. Las exclusiones por estado,
periodo, fuente y disponibilidad deben acompanarse de su contexto analitico.

No se ejecutaron pruebas de carga ni ataques en produccion como parte de esta
subrevision. La capacidad, el aislamiento entre cuentas y la interfaz se revisan
por separado.
