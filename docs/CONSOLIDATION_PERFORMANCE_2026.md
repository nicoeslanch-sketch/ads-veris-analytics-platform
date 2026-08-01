# Aceptación de recursos — consolidación 2026

Fecha de medición: 2026-07-31. Baseline de código: `1dc0416`. Las fuentes reales
se leyeron localmente y no se copiaron al repositorio. Durante esta medición la
migración 0022 aún no estaba aplicada; se verificó aplicada en producción el
1 de agosto de 2026.

## Resultado ejecutivo

| Escenario | Versión | Estado | Peak RSS real | Duración medida |
|---|---|---:|---:|---:|
| Con Archivo B | baseline | VALID_WITH_WARNINGS | 499.646.464 B (476,5 MiB) | 549,5 s de pared |
| Con Archivo B | optimizada | VALID_WITH_WARNINGS | 430.972.928 B (411,0 MiB) | 374,0 s instrumentados; 377,1 s de pared |
| Sin Archivo B | baseline | PARTIAL | 454.258.688 B (433,2 MiB) | 491,2 s de pared |
| Sin Archivo B | optimizada | PARTIAL | 435.044.352 B (414,9 MiB) | 361,1 s instrumentados; 363,9 s de pared |

Con B, el peak bajó 68.673.536 B (13,7%). Sin B bajó 19.214.336 B
(4,2%). Los dos quedan holgadamente bajo el soft limit de 3 GB y son aptos para
un worker de 4 GB con concurrencia 1. La cifra previa de 961.269.810 B
(aprox. 916,7 MiB) era una suma `DataFrame.memory_usage(deep=True)`, no el peak
RSS del proceso.

El CLI baseline releía el XLSX completo solo para volver a contar filas. La
versión final usa los conteos y el hash recogidos durante la escritura, por lo
que evita aproximadamente 160–200 s de trabajo redundante. Las duraciones
baseline de pared incluyen esa relectura; las instrumentadas optimizadas cubren
fuentes, transformación, calidad, exportación y liberación.

## Equivalencia funcional

Ambos escenarios conservaron:

- 128.345 filas, 128.345 `ID_aux` únicos y 92 columnas en el mismo orden;
- cero multiplicación de filas;
- cobertura de `tipo_de_enseñanza` 0,9925279520 con B;
- D: 119.893 coincidencias únicas, 0 ambiguas y 8.452 ausentes;
- Oferta: 2 códigos ambiguos, 2.150 códigos resueltos, 128.345 filas de
  Matrícula cubiertas y 0 sin catálogo;
- `cohorte_id = 2026:{id_aux}` como `generated_fallback` pendiente de evidencia
  histórica.

Hash lógico de `BASE DE DATOS` (los metadatos ZIP/XLSX no participan):

| Escenario | Baseline | Optimizada | Resultado |
|---|---|---|---|
| Con B | `0b9723495ba2228069f3ad53868e0fcc3dc27a44f4eb5e3d823882fbddf57269` | igual | coincide |
| Sin B | `c15324c60b531b3ee819cf34d84ef6503399dac6051625662d19f68a9095c4f6` | igual | coincide |

## RSS y tiempos por etapa, ejecución optimizada con B

| Etapa | RSS antes | RSS después | Tiempo | Filas/chunks |
|---|---:|---:|---:|---:|
| Preparación/hash de fuentes | 108,8 MB | 108,8 MB | 2,61 s | 10 fuentes |
| Matrícula | 108,8 MB | 123,3 MB | 0,16 s | 128.345 / 2 |
| Archivo B | 227,0 MB | 257,3 MB | 2,46 s | 317.700 / 4 |
| Archivo C | 280,8 MB | 263,2 MB | 2,06 s | 317.700 / 4 |
| Archivo D | 274,3 MB | 284,5 MB | 7,44 s | 1.686.689 / 17 |
| Oferta filtrada | 284,5 MB | 274,7 MB | 230,07 s | 396.003 / 4; 29.911 retenidas |
| Mapping acumulado | 125,6 MB | 346,7 MB | 4,72 s | 6 pasos |
| Consolidación | 326,1 MB | 330,2 MB | 0,08 s | 128.345 |
| Calidad | 330,2 MB | 426,9 MB | 3,48 s | 128.345 |
| Exportación anual | 430,4 MB | 430,7 MB | 115,71 s | 128.345 / 2 |
| Auditoría | 430,7 MB | 430,7 MB | 0,04 s | 76 filas agregadas |
| Liberación | 431,0 MB | 258,4 MB | 0,09 s | 172,6 MB liberados desde peak |

El muestreador final atribuye además el peak local de cada etapa sin registrar
valores de filas. La etapa dominante en tiempo es la lectura XML del XLSX de
Oferta; no representa presión de memoria.

## Disco y artefactos

En aceptación local las fuentes permanecieron fuera del scratch y nunca se
copiaron. Los artefactos ocuparon:

- con B: anual 26.060.078 B, auditoría 9.318 B y manifest aproximadamente 37 KB;
- sin B: anual 22.388.738 B, auditoría 9.408 B y manifest aproximadamente 37 KB.

En producción, el directorio aislado también contendrá las descargas: el total
de fuentes con B es 543.402.308 B. Se exige un mínimo configurable de 10 GB y se
recomiendan 10–20 GB para variaciones, reintentos y exportación histórica.

## Archivo D: reconciliación de conteos

La cifra 1.154.969 provenía de una especificación inicial que describía otro
perfil de D con 8 columnas. No fue una medición del CSV finalmente encontrado.
El archivo real, fuente de verdad, contiene una cabecera y 1.686.689 registros,
6 columnas, 188.538 IDs distintos, 0 IDs vacíos, 0 cabeceras repetidas y 0 filas
exactamente duplicadas (hash de las seis columnas). El pipeline leyó el archivo
una sola vez en 17 chunks; 1.147.627 registros pertenecían al universo de
Matrícula. No se concatenaron archivos, hojas ni encabezados.

## Clasificación de las 55 columnas totalmente vacías

El manifest específico registra cada columna sin inventar valores:

- 4 `available_but_not_detected`: `rama_educacional`, `provincia`,
  `vacantes_b`, `NIVEL_GLOBAL`;
- 3 `mapping_pending`: `dependencia`, `percentil_nem`, `tipo_plan_estudio`;
- 13 `really_not_available_2026`: variables sin equivalente demostrado en las
  fuentes 2026;
- 9 `source_not_provided`: ID y nombres institucionales de trayectorias;
- 26 `future_historical_variable`: trayectorias y retención que requieren
  observaciones posteriores.

Las cuatro variables detectables y las tres pendientes siguen nulas para
conservar equivalencia con el baseline. Deben certificarse mediante una nueva
versión editable del manifest, no inferirse durante esta optimización.

## Riesgos residuales

- Oferta tarda cerca de cuatro minutos con OpenPyXL; es el próximo candidato a
  optimización de CPU/lectura XML, no un riesgo de RAM.
- El fallback de `cohorte_id` impide certificar una consolidación histórica
  hasta validar la clave autoritativa.
- El worker y los flags del backend deben aceptarse con una ejecución
  autenticada de extremo a extremo; la migración 0022 ya está aplicada.
- Concurrencia mayor que 1 por proceso se rechaza deliberadamente. Escalar
  horizontalmente hasta contar con otra prueba de presupuesto.
