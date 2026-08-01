# Consolidación y recodificación

Implementación aislada dentro de Estandarización. No sustituye ni modifica el
pipeline clásico.

El modo predeterminado es **General** y no presupone un sector ni nombres de
columnas. El usuario elige el archivo principal, la clave de cada unión y las
tablas de equivalencias. **Educación / DEMRE 2026** se conserva como plantilla
especializada opcional para los proyectos anteriores.

## Modo general

- El archivo principal conserva todas sus filas y columnas. Su clave puede
  repetirse (por ejemplo, varias ventas del mismo producto).
- Hasta cuatro archivos complementarios aportan columnas mediante una relación
  muchos-a-uno. La clave del complemento debe ser única; las claves ambiguas se
  excluyen y se informan, nunca multiplican filas.
- Hasta dos tablas de equivalencias traducen códigos a una columna nueva sin
  borrar el valor original.
- CSV detecta separador entre coma, punto y coma, tabulador y barra vertical;
  XLSX permite elegir la hoja.
- El histórico opcional se apila solo si sus columnas coinciden exactamente.
- Los artefactos se llaman `BASE_CONSOLIDADA.xlsx`,
  `AUDITORIA_CONSOLIDACION.xlsx` y `manifest.json`.

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

- `GET /consolidation/status`
- `GET /consolidation/datasets/{dataset_id}/inspect`
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

## Estado de producción

`0022_consolidation_domain.sql` crea cinco tablas aditivas con RLS, ownership,
FKs, checks, índices e idempotencia. El 1 de agosto de 2026 se comprobó que:

- la migración `0022_consolidation_domain` está registrada en Supabase;
- las cinco tablas existen con RLS y políticas de lectura por propietario;
- la API productiva responde `/health` y `/version`;
- `/version` declara entorno `production`, motor `0.25.0`, migración `0022` y
  el SHA `aba2d5a8639b7be2f39a1ee23923bbbdc0a06b81`.

La release `0.26.0` requiere además `0023_general_consolidation.sql`, que amplía
los roles permitidos sin eliminar los roles DEMRE. El worker y los flags del
backend se aceptan observando una ejecución autenticada pasar de `queued` a
`running` y a un estado terminal; no se infieren solo desde el frontend.

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

Si el runtime no permite que `psutil` inspeccione el proceso, la telemetría usa
el high-water mark de `getrusage` como respaldo conservador y lo declara en
`resource_metrics.memory_backend`. En ese modo puede comprobar límites, aunque
no calcular memoria liberada con la misma precisión.

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

## Aceptación manual en producción

Use una cuenta administradora y fuentes de prueba que ya estén cargadas en el
Historial. No use datos personales reales para el primer smoke test.

1. Abra **Estandarización** y seleccione **Consolidar y recodificar archivos**.
2. Cree un trabajo en modo General, sin histórico para que la primera prueba sea corta.
3. Seleccione un archivo principal y su clave. Agregue un complemento pequeño
   con una clave única equivalente y, si corresponde, una tabla de equivalencias.
4. Valide. Sin archivo principal o sin una clave elegida debe bloquear.
5. Prepare la previsualización. El run debe abandonar `queued`, pasar por
   `running` y terminar en `valid_with_warnings`, `partial` o `certified`.
   Si permanece en `queued` más de 30 segundos, revise el servicio worker.
6. Compruebe que la muestra no exponga más de 100 filas y que las filas finales
   coincidan exactamente con las filas del archivo principal.
7. Genere los artefactos y descargue `annual`, `audit` y `manifest`. El Excel
   anual debe conservar todas las filas originales y agregar solo las columnas
   relacionadas o recodificadas.
8. Pulse **Usar resultado en la plataforma** solo después de revisar esos tres
   archivos. Debe aparecer un dataset derivado en el Historial.
9. En Supabase deben existir, para ese usuario, un proyecto, sus fuentes, dos
   runs como máximo (preview/full; el segundo puede reutilizar el primero) y
   artefactos inmutables bajo `.consolidation`.

Pruebe después tres fallos controlados: clave vacía en el principal, clave
duplicada en el complemento y código sin equivalencia. Ninguno debe multiplicar
filas ni producir una descarga certificada silenciosamente. La plantilla DEMRE
mantiene su checklist sectorial anterior y sus 92 columnas.

## Rollback

1. `CONSOLIDATION_ENABLED=false`.
2. `VITE_CONSOLIDATION_ENABLED=false` y reconstruir el frontend cuando proceda.
3. Detener el worker.
4. Conservar o eliminar únicamente artefactos derivados.

No es necesario revertir el pipeline clásico, reconstruir snapshots ni eliminar
las tablas aditivas.
