# Consolidación y recodificación

Implementación aislada dentro de Estandarización. No sustituye ni modifica el
pipeline clásico.

## Seguridad y límites

- JWT y ownership de todos los `dataset_id` en cada proyecto.
- Solo administradores durante el piloto.
- Backend y frontend apagados por defecto.
- La API nunca acepta rutas locales. El worker descarga fuentes desde Storage a
  temporales generados y los elimina al terminar.
- El límite clásico de 15 MB permanece intacto. El dominio usa
  `CONSOLIDATION_MAX_SOURCE_MB` exclusivamente detrás del flag.
- No hay llamadas a IA ni logs de filas, ID, nombres o puntajes individuales.
- La telemetría contiene solo RSS, tiempos, filas, chunks y bytes agregados.
- Los artefactos usan nombres inmutables bajo
  `{user_id}/.consolidation/{project_id}/{run_id}/`.

## API

- `POST /consolidation/projects`
- `GET /consolidation/projects/{project_id}`
- `PUT /consolidation/projects/{project_id}/sources`
- `POST /consolidation/projects/{project_id}/validate`
- `POST /consolidation/projects/{project_id}/preview`
- `POST /consolidation/projects/{project_id}/runs`
- `GET /consolidation/runs/{run_id}`
- `GET /consolidation/runs/{run_id}/report`
- `GET /consolidation/runs/{run_id}/export/{kind}`
- `POST /consolidation/runs/{run_id}/activate`

`activate` es la única acción que registra el resultado como dataset derivado y
requiere una confirmación explícita del usuario.

## Decisiones conservadoras de la plantilla DEMRE 2026

- Matrícula define filas y autoridad sobre ID, carrera, vía, preferencia y
  puntaje ponderado.
- `RBD` del Archivo B se declara como alias de `ID_RBD` del libro.
- B tiene precedencia demográfica; C, para clasificación educacional y puntajes
  efectivamente presentes.
- D se reduce por `ID_aux`, misma carrera y estado de selección leído del libro.
  Cero, una o varias coincidencias producen `d_no_match`, `d_match_unique` o
  `d_ambiguous`; nunca se elige first/last.
- Oferta primero filtra `OFE_2026`. Solo acepta una firma única o una firma única
  con `Vigente con estudiantes nuevos`; el resto queda `offer_ambiguous`.
- El histórico real no contiene `cohorte_id`; la primera versión genera
  `cohorte:id_aux` y lo marca `generated_fallback`.
- Las columnas sin fuente permanecen vacías y aparecen en la auditoría con
  `unsupported_in_2026` o `source_value_missing`.
- La plantilla de 92 columnas es el manifest DEMRE predeterminado, pero la API
  admite otra lista única y ordenada por proyecto.

## Migración pendiente

`0022_consolidation_domain.sql` crea cinco tablas aditivas con RLS, ownership,
FKs, checks, índices e idempotencia. Para aplicarla posteriormente:

1. respaldar y revisar el proyecto Supabase objetivo;
2. ejecutar las migraciones mediante el procedimiento habitual del proyecto;
3. comprobar que existen las cinco tablas y sus políticas RLS;
4. mantener ambos flags apagados y probar la API como administrador;
5. arrancar el worker y recién después encender backend y frontend.

## Ejecución local

Desde `api/`:

La API web y el worker son procesos distintos. La API se inicia con el comando
habitual de FastAPI y nunca ejecuta archivos grandes dentro de una solicitud.
El worker consume la cola persistente:

```powershell
python -m app.consolidation.worker
```

Para aceptación con archivos locales use el CLI separado:

```powershell
python -m scripts.run_consolidation_local --source matricula=C:\ruta\matricula.csv --source archivo_c=C:\ruta\c.csv --output C:\salida-nueva
```

Repita el argumento `--source` para cada rol. La carpeta de salida debe ser
nueva: ninguna exportación sobrescribe otra.

## Recursos y telemetría

Valores iniciales seguros, todos configurables por entorno:

```dotenv
CONSOLIDATION_WORKER_CONCURRENCY=1
CONSOLIDATION_MEMORY_SOFT_LIMIT_MB=3000
CONSOLIDATION_MEMORY_HARD_LIMIT_MB=3600
CONSOLIDATION_TEMP_DIR=
CONSOLIDATION_TEMP_DISK_MIN_MB=10240
CONSOLIDATION_CHUNK_SIZE=100000
CONSOLIDATION_PREVIEW_ROWS=100
CONSOLIDATION_RUN_STALE_SECONDS=21600
```

El límite se aplica solo al dominio nuevo. El muestreador usa RSS del proceso y
el high-water mark del sistema operativo. Superar el límite blando deja una
advertencia agregada; superar el duro detiene el run con
`memory_hard_limit_exceeded`, lo marca `failed` y conserva métricas auditables.
El espacio temporal se valida antes de empezar; la falta de capacidad produce
`temporary_disk_insufficient`. Cada run usa un directorio aislado que se borra
en `finally` tanto al completar como al fallar.

D y las dimensiones CSV se leen por chunks. B/C conservan solo columnas útiles
y IDs del universo de Matrícula. Oferta filtra `OFE_<cohorte>` durante la
lectura y los libros de códigos se cierran inmediatamente. Los XLSX derivados
se escriben en modo `write_only`; el hash lógico se calcula durante la misma
escritura y la previsualización se limita en backend.

## Topología de producción

- **API:** 1–2 GB RAM, 1–2 vCPU. Valida JWT/ownership, crea runs y consulta
  estado; no necesita disco temporal grande.
- **Worker inicial:** 4 GB RAM, 2 vCPU recomendadas, concurrencia 1 y 10–20 GB
  de disco temporal. La RAM corresponde al servicio del worker, nunca al
  frontend de Vercel.
- **Storage:** privado y accesible por ambos servicios. Solo los artefactos
  derivados ya subidos correctamente se preservan.

Render, Railway, Fly.io, Cloud Run, una VM o contenedores pueden representar la
misma topología con dos servicios que usan la misma imagen: uno ejecuta el
comando web y otro `python -m app.consolidation.worker`. En plataformas con
filesystem efímero, monte o asigne 10–20 GB al directorio temporal del worker.
No configure más de un trabajo dentro del mismo proceso. Para escalar, agregue
workers de 4 GB horizontalmente: la reclamación condicional de la cola evita
que dos workers tomen el mismo run. Antes de aumentar concurrencia por proceso,
repita la aceptación con un presupuesto de memoria explícito.

Los runs `running` abandonados se reencolan después del umbral configurable.
Los artefactos siguen siendo inmutables: ante un `409`, el worker descarga y
compara SHA-256; solo reutiliza el objeto si es idéntico, nunca lo sobrescribe.

Resultados y mediciones reales: [CONSOLIDATION_PERFORMANCE_2026.md](./CONSOLIDATION_PERFORMANCE_2026.md).

## Rollback

1. `CONSOLIDATION_ENABLED=false`.
2. `VITE_CONSOLIDATION_ENABLED=false` y reconstruir el frontend cuando proceda.
3. Detener el worker.
4. Conservar o eliminar únicamente artefactos derivados.

No es necesario revertir el pipeline clásico, reconstruir snapshots ni eliminar
las tablas aditivas.
