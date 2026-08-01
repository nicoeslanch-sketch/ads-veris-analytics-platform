# Aceptación real de consolidación 2026

Fecha: 2026-08-01. Los diez archivos reales se leyeron desde una ubicación local fuera del repositorio; no se
copiaron al repositorio ni se registraron filas o datos personales.

| Escenario | Estado | Filas base/finales | Columnas | Duración | Peak RSS |
|---|---|---:|---:|---:|---:|
| DEMRE completo con B | `VALID_WITH_WARNINGS` | 128.345 / 128.345 | 92 | 405,8 s | 603.013.120 B |
| DEMRE sin B | `PARTIAL` | 128.345 / 128.345 | 92 | 465,8 s | 589.541.376 B |
| General: base + 2 complementos + equivalencia | `VALID_WITH_WARNINGS` | 4 / 4 | 10 | prueba subsegundo | bajo presupuesto de tests |

## Resultado DEMRE completo

- B: 317.700 filas leídas, 128.345 del universo, 128.345 relaciones seguras,
  0 claves ambiguas.
- C: mismos conteos y 0 claves ambiguas.
- D: 1.686.689 filas, 119.893 selecciones únicas, 0 ambiguas y 8.452 sin
  coincidencia seleccionada.
- Oferta: 396.003 filas examinadas, 29.911 del periodo, 2.150 códigos resueltos,
  2 ambiguos excluidos y 0 matrículas sin catálogo.
- Recodificación: `VIA` 128.345/128.345; `TIPO_MATRICULA`
  128.345/128.345 en auditoría; sexo 100%; país 100%; rama 99,2528% (959
  fuentes vacías).
- Hash lógico anual:
  `d7883f1890255e5c6c7b143d3dea3de525c48d88aa5aa7c0ba7e6309980b4696`.

Artefactos locales: `DEMRE_2026_COMPATIBLE.xlsx` (36.915.128 B),
`AUDITORIA_CONSOLIDACION_DEMRE_2026.xlsx` y `manifest.json`.

## Resultado sin B

La ausencia de B no se cubre con su libro. El manifest incluye
`source_b_missing`; campos exclusivos quedan nulos con motivo. C, D, Oferta y
Libro Matrícula siguen activos. Resultado: 128.345 filas, 92 columnas,
`PARTIAL`, hash lógico
`9e62ad2196a66ad5036de65b5bbf6938618f1e3f4ff76d68ba7ce699a558caca`.

## Caso general

Ventas conservó 4/4 filas. Productos incluyó una clave conflictiva: se excluyó
sin multiplicar dos ventas. Clientes agregó sus columnas con relación segura.
La tabla de estados tradujo tres códigos y dejó uno sin equivalencia, conservando
el código original. Estado final `VALID_WITH_WARNINGS`.

## Recursos y riesgo residual

La Oferta XLSX domina el tiempo (216–256 s) y la exportación anual tarda
151–163 s. El peak queda muy por debajo del límite blando de 3 GB y es apto para
el worker recomendado de 4 GB/concurrencia 1. La exportación histórica completa
supera una hoja Excel; el motor la divide determinísticamente en varias hojas.
La optimización futura prioritaria es la lectura XML de Oferta, no aumentar RAM.
