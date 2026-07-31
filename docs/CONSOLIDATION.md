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

```powershell
python -m app.consolidation.worker
```

Para aceptación con archivos locales use el CLI separado:

```powershell
python scripts/run_consolidation_local.py --source matricula=C:\ruta\matricula.csv --source archivo_c=C:\ruta\c.csv --output C:\salida-nueva
```

Repita el argumento `--source` para cada rol. La carpeta de salida debe ser
nueva: ninguna exportación sobrescribe otra.

## Rollback

1. `CONSOLIDATION_ENABLED=false`.
2. `VITE_CONSOLIDATION_ENABLED=false` y reconstruir el frontend cuando proceda.
3. Detener el worker.
4. Conservar o eliminar únicamente artefactos derivados.

No es necesario revertir el pipeline clásico, reconstruir snapshots ni eliminar
las tablas aditivas.
