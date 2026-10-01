# Sesiones revocadas y eliminacion de cuentas

Migracion aplicada: `20260930095641_revoked_session_guards.sql`. La version
corresponde a la fecha generada por Supabase al aplicar. No modifica ni elimina
cuentas o archivos existentes.

## Correccion

Validar la firma y la caducidad de un JWT no demuestra que su sesion siga activa.
La API consultaba el requisito MFA para AAL1, pero omitia la consulta para AAL2.
Las politicas RLS tampoco comprobaban la existencia de la sesion.

Se agrega una consulta privada, limitada a booleanos, que vincula `sub` y
`session_id` con `auth.sessions` y `auth.users`. Rechaza sesiones eliminadas,
vencidas por `not_after`, cuentas suspendidas y cuentas eliminadas. Tambien se
aplica a AAL2, al endpoint de configuracion de seguridad y a las politicas
restrictivas existentes de las tablas publicas y Storage.

No se cachean decisiones de autorizacion. Dentro de una misma peticion se
reutiliza el resultado, evitando dos consultas para comprobar sesion y MFA.
Los clientes siguen pudiendo usar correo y contrasena sin habilitar MFA; el
segundo factor permanece obligatorio solo para administradores y para quien
lo haya activado voluntariamente.

## Verificacion

- Pruebas unitarias de revocacion AAL1/AAL2, identidad, entrada malformada,
  indisponibilidad y ausencia de cache de autorizacion.
- Laboratorio PostgreSQL/Auth aislado: inicio de sesion, TOTP, cierre global
  real y reutilizacion del token previo. El token revocado debe perder acceso
  directo por RLS y a una descarga real de Storage; la consulta privada debe
  indicar sesion inactiva.
- Controles positivos de sesiones vigentes, aislamiento entre usuarios,
  `not_after`, suspension, eliminacion logica y eliminacion por Auth Admin.
- Las pruebas destructivas se limitan a cuentas sinteticas en localhost.

## Dependencia de autenticacion

PyJWT se actualiza de 2.13.0 a 2.15.0 por los avisos publicados el 29 y 30 de
septiembre, detectados por Dependabot y por el control obligatorio de CI.
Incluye correcciones de validacion de claves, cabeceras JSON malformadas y
obtencion de JWKS. No se omiten ni silencian alertas. Se agrega una regresion
para que una cabecera o carga util profundamente anidada produzca 401, no un
error 500. La carga util se prueba con el cliente JWKS real y debe fallar antes
de intentar descargar claves.
El caso critico de mezcla HS/asimetrica no coincide con nuestra separacion
de algoritmos, pero eso no justifica conservar una dependencia vulnerable.

Fuentes:
- https://github.com/jpadilla/pyjwt/releases/tag/2.14.0
- https://github.com/jpadilla/pyjwt/releases/tag/2.15.0

## Conversacion del asistente

Se probaron preguntas de recuperacion de clave, TOTP, QR, obligatoriedad,
perdida de factores, cierre de sesion y cierre de cuenta. Antes del cambio,
17 de los 20 casos iniciales fallaban: el motor enviaba preguntas de acceso a
respuestas de tarjetas, proyecciones o importacion. La version corregida pasa
23 casos, incluyendo una conversacion encadenada de diez turnos y protecciones
para no interpretar claves bancarias como recuperacion de acceso.

El diccionario conserva palabras validas como `recupero`, `cerre` y `escanear`,
que antes se corregian erroneamente como `recupera`, `cierre` y `estandar`.
Se toleran consultas pegadas y errores comunes sin ejecutar acciones ni
solicitar claves. El bot sigue siendo determinista, no un modelo generativo.

## Eliminacion integral

Desde la migracion `20261001010500`, el panel administrador incorpora un
ejecutor integral para solicitudes de eliminacion verificadas. El proceso:

1. bloquea la cuenta y cancela trabajos pendientes;
2. enumera y elimina originales y artefactos internos bajo el prefijo privado;
3. exige una segunda enumeracion vacia de Storage;
4. purga caches locales y Redis indexadas por titular;
5. elimina el usuario de Auth para activar las cascadas de base de datos; y
6. conserva un comprobante tecnico sin email, nombres de archivo ni contenido.

La operacion es idempotente y un fallo intermedio queda registrado para
reintento. No borra cuentas administradoras ni permite que un administrador
se elimine a si mismo desde ese flujo. Las copias de recuperacion cifradas no
se editan retrospectivamente: deben vencer segun la retencion documentada y,
si se restaura una copia anterior, la lista de supresion debe reaplicarse antes
de reabrir el servicio.

Una peticion ya autorizada y en curso no se cancela retroactivamente. Una URL
firmada de Storage ya emitida puede funcionar hasta su vencimiento (actualmente
cinco minutos), salvo que se elimine antes el objeto. No se ha eliminado ningun
cliente real durante la validacion.

El proveedor confirma que eliminar `auth.users` no invalida por si solo los JWT
emitidos: https://supabase.com/docs/guides/auth/managing-user-data
