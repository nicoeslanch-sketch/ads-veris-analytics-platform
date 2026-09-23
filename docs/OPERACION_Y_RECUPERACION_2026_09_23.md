# Recuperacion y alertas

## Evidencia, no certificacion

Laboratorio de recuperacion aprobado: GitHub Actions run 35844587521, commit
60f74e3. Se uso Supabase desechable, una cuenta ficticia y un CSV sintetico.
No se leyeron ni copiaron datos de produccion. PostgreSQL, Auth y Storage se
restauraron sobre la misma version base del proveedor y las mismas migraciones.

Se verifico integridad del repositorio restic, rechazo de un productor truncado,
metadatos de dataset identicos, bytes del CSV identicos, inicio de sesion con la
contrasena restaurada, acceso por propietario y RPC privadas inaccesibles.
El destino con datos existentes fue rechazado. Los tiempos de este archivo
pequeno NO son RTO de produccion. Se agrego otra comprobacion de ownership de
Storage y acceso autenticado al archivo: aprobados tambien en el run 35846417096
(commit 4b02054), incluido rechazo de descarga anonima.

Pendiente para datos reales: destino de respaldo confirmado por el titular,
credenciales protegidas, copia inicial, verificacion, responsable de operacion,
frecuencia y ensayo representativo. El laboratorio no resuelve esos pendientes.

## Procedimiento de respaldo

Herramientas: cliente PostgreSQL de version mayor igual o superior a la del
servidor, restic (laboratorio: 0.19.1) y Python/httpx. No hay formato de cifrado
propio: restic cifra y autentica el repositorio. ZIP es solo el contenedor interno.

1. Aprobar un destino independiente de Supabase. Una carpeta en el mismo PC es
   util para el primer ensayo, pero no cubre perdida o robo de ese equipo.
2. Configurar mediante secretos del operador, nunca comandos guardados ni Git:
   `ADS_BACKUP_DB_URL`, `ADS_BACKUP_STORAGE_URL`, `ADS_BACKUP_SERVICE_KEY`,
   `RESTIC_REPOSITORY` y `RESTIC_PASSWORD_FILE`. Proteger el archivo de clave con
   permisos exclusivos y custodiar una copia de recuperacion por separado.
3. Validar TLS PostgreSQL con `verify-full` y su certificado CA. No degradar a
   `require` ni desactivar la validacion para solucionar un error de conexion.
4. Inicializar el repositorio una sola vez con `restic init`. Ejecutar
   `python scripts/recovery_backup.py check` antes de la primera copia.
5. En una ventana sin escrituras/subidas/borrados, ejecutar
   `python scripts/recovery_backup.py backup`. El inventario Storage se compara
   antes y despues. Un cambio aborta la copia, no publica un snapshot incompleto.
6. Ejecutar `restic check --read-data` y revisar fecha y resultado de la copia.
   No basta con que el comando haya arrancado. No activar purgas automaticas
   antes de aprobar retencion y verificar una restauracion.

Alcance: esquemas `public`, `app_private`, `auth`, `storage` y objetos Storage.
Se excluyen datos del historial de migraciones del proveedor; el destino debe
tener las mismas migraciones. No son PITR ni un snapshot atomico PostgreSQL/S3.
Por eso se exige ventana sin modificaciones. Los datos viajan por streaming al
cifrado, sin escribir primero un dump abierto en disco.

Guardar aparte un inventario operativo de versiones, migraciones, buckets,
configuracion de Auth/SMTP/OAuth, dominios, variables requeridas y secretos raiz
del proveedor que correspondan. Las contrasenas de roles PostgreSQL, ajustes de
plataforma y claves de cifrado raiz no se recuperan desde este dump.

## Restauracion aislada

1. Crear una instancia desechable local de la misma version del proveedor y
   ejecutar las migraciones exactas. No restaurar encima del servicio activo.
2. Desencriptar la copia elegida en una carpeta temporal con permisos exclusivos.
   Este paso SI materializa datos sensibles: no usar una carpeta sincronizada.
3. Ejecutar `python scripts/recovery_backup.py verify --archive RUTA`.
4. Configurar `ADS_RESTORE_DB_URL`, `ADS_RESTORE_STORAGE_URL` y
   `ADS_RESTORE_SERVICE_KEY` solo para esa instancia literal loopback. El rol
   administrador local es necesario para Auth/Storage; no ampliar privilegios
   del rol de la aplicacion alojada.
5. Ejecutar `python scripts/recovery_restore_local.py --archive RUTA --confirm-empty-local`.
   El comando rechaza destinos remotos, usuarios/archivos preexistentes y
   migraciones distintas. Un fallo requiere revisar o recrear el destino aislado.
6. Comparar totales de tablas, relaciones, identidades y hashes de archivos;
   probar login, aislamiento entre cuentas, descarga y un analisis conocido.
   Registrar tiempo real de restauracion y antiguedad de la copia elegida.
7. Retirar archivos temporales mediante un procedimiento del operador para su
   disco cifrado. Un borrado ordinario no garantiza borrado forense de un SSD.

La herramienta no cambia DNS ni ejecuta una restauracion remota. Una migracion
a otro proyecto Supabase requiere revisar diferencias de versiones, roles,
secretos raiz y politicas antes de aprobarla. No anunciar recuperacion ante
desastre de produccion como completa hasta ensayar ese escenario.

## Alertas operativas

El backend conserva contadores acotados de cinco minutos y publica un latido
privado cada 60 segundos. La RPC solo admite service_role. El panel administrativo
consulta al abrir y cada minuto mientras permanece abierto; al fallar, no sigue
mostrando un estado saludable antiguo. No guarda contenido de archivos ni preguntas.

Umbrales iniciales: errores HTTP (minimo 5 y 5%), limitados (10 y 10%), lentos
(10 y 20%), espera en cola superior a 120 s, cola/almacenamiento al 80%, leases
vencidos, trabajos de mas de 20 min, reservas de mas de 30 min y tamanos pendientes.
Son umbrales revisables, no un SLA. Las fallas recientes de cola son las que
siguen retenidas, no un historial permanente de todos los trabajos.

`Public availability` comprueba web y `/health` cada 15 minutos solicitados,
con tres intentos acotados. Usa solo URLs publicas; no secretos de produccion.
Abre una incidencia GitHub por caida persistente, no repite avisos sin cambios y
la cierra al recuperar ambas respuestas. Un HTTP sano no prueba que login,
Storage, base de datos o analisis completo esten funcionando. Las alertas de
saturacion internas todavia no se envian a un destino externo.

GitHub puede retrasar/omitir ejecuciones o desactivar cron tras inactividad del
repositorio publico. Los correos dependen de las preferencias de notificacion
del propietario: configurar Watch para issues y correo, y probar la recepcion.
Esto no sustituye una guardia ni un monitor con disponibilidad garantizada.

Fuentes oficiales consultadas:
- https://www.postgresql.org/docs/current/app-pgdump.html
- https://supabase.com/docs/guides/platform/backups
- https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/subscriptions-and-notifications/get-started/configuring-notifications
