# Consolidación y recodificación

Dominio aislado dentro de **Estandarización**. No sustituye el flujo clásico,
no envía datos a IA y permanece apagado por defecto y limitado a
administradores.

## Experiencia de cuatro pasos

1. **Cargar:** nombre, periodo, carga múltiple CSV/XLSX y selección de datasets
   existentes. Cada carga muestra progreso, permite cancelar, reintentar y
   quitar. Usa el mismo bucket `datasets`, ownership y RLS del flujo existente.
2. **Revisar:** `POST /consolidation/detect` inspecciona hojas, encabezados,
   muestras estructurales acotadas y SHA-256. Propone archivo base, relaciones,
   equivalencias, histórico o plantilla DEMRE con confianza explicable. Las
   opciones técnicas permanecen plegadas.
3. **Comprobar:** crea internamente el proyecto, valida y ejecuta un dry-run.
   Reúne filas, relaciones, ambigüedades, recodificación, calidad y muestra
   segura paginada. Identificadores, RUT, nombres, correos, teléfonos y
   direcciones se excluyen de la previsualización genérica.
4. **Obtener resultado:** procesa en el worker durable, muestra eventos por
   etapa, descargas con nombres comprensibles y la acción explícita para usar
   la base derivada en la plataforma.

El modo general conserva todas las filas del archivo base. Solo incorpora
relaciones muchos-a-uno seguras. Una clave repetida en el archivo relacionado
se excluye; nunca se resuelve con `first`, `last` ni `keep="first"`.

## Detección

La detección usa encabezados normalizados, hojas, cantidad aproximada de filas,
unicidad en una muestra acotada, columnas comunes y estructura de libros. El
nombre puede aportar contexto visual, pero no decide roles. Si hay dos claves
razonables se solicita confirmación y no se elige una arbitrariamente.

La API nunca recibe rutas locales. Descarga solo datasets del usuario desde
Storage, con límite exclusivo `CONSOLIDATION_MAX_SOURCE_MB`, calcula SHA-256 y
elimina el temporal. La carga directa no aumenta el límite del flujo clásico.

## Contrato DEMRE aprobado

`target_schema.py` reproduce exactamente el encabezado y orden de la hoja
`BASE DE DATOS` de `DEMRE 2020-2025_ACTUALIZADA.xlsx`: 92 columnas desde
`id_aux`, `cohorte`, `nac_rec` hasta `cuartiles_Matematica_elect`, `Edad_Q4`.
No contiene `cohorte_id`, retención ni seguimiento inventado. Los tipos lógicos
texto/número también están declarados.

Reglas conservadoras:

- Matrícula define 128.345 filas y una fila final por `ID_aux`.
- El alias `RBD ↔ ID_RBD` existe solo en el manifest DEMRE.
- B y C deben ser una-a-una; duplicados quedan fuera y se auditan.
- D se reduce por persona, misma carrera y estado de selección leído del Libro D.
- Oferta se filtra a `OFE_2026` y solo acepta firma única o vigencia declarada.
- Libro Matrícula traduce realmente `VIA` hacia `via2`. También traduce
  `TIPO_MATRICULA`, pero lo conserva en auditoría porque el histórico aprobado
  no posee una columna equivalente.
- Libro B traduce sexo, rama y país; Libro C aporta la rama como precedencia de
  respaldo; Libro D determina estados de selección.
- `Pref_rec1`, `Pref_rec2`, `VIA_rec1`, `rama1` y `Dep` son derivaciones
  declarativas, versionadas y auditables.
- Toda columna sin fuente queda nula con `reason_code`. No se calculan cuartiles
  sin la metodología histórica aprobada.

El histórico real ya ocupa el máximo de 1.048.576 filas de una hoja Excel. La
exportación consolidada crea hojas consecutivas con el mismo encabezado, en vez
de perder filas o producir un archivo inválido.

## API y procesos

- `GET /consolidation/status`
- `POST /consolidation/detect`
- `GET /consolidation/datasets/{dataset_id}/inspect`
- `POST /consolidation/projects`
- `PUT /consolidation/projects/{project_id}/sources`
- `POST /consolidation/projects/{project_id}/validate`
- `POST /consolidation/projects/{project_id}/preview`
- `POST /consolidation/projects/{project_id}/runs`
- `GET /consolidation/runs/{run_id}`
- `GET /consolidation/runs/{run_id}/export/{kind}`
- `POST /consolidation/runs/{run_id}/activate`

El worker se ejecuta separado con `python -m app.consolidation.worker`,
concurrencia 1, scratch aislado, límites de memoria/disco, recuperación de runs
interrumpidos, idempotencia y eventos por etapa en
`consolidation_run_events`. Los XLSX neutralizan celdas que comienzan con
`=`, `+`, `-` o `@`; cada artefacto lleva SHA-256 y nunca se sobrescribe.

No se requirió una migración nueva: se reutilizan las tablas de 0022, los roles
aditivos de 0023 y la tabla de eventos ya existente.

## Flags, despliegue y rollback

```dotenv
CONSOLIDATION_ENABLED=false
CONSOLIDATION_ADMIN_ONLY=true
CONSOLIDATION_WORKER_CONCURRENCY=1
VITE_CONSOLIDATION_ENABLED=false
```

Rollback: apagar ambos flags y detener el worker. No se elimina ninguna fuente,
tabla ni artefacto automáticamente y el flujo clásico queda intacto.

Mediciones reales: [CONSOLIDATION_PERFORMANCE_2026.md](./CONSOLIDATION_PERFORMANCE_2026.md).
