# Sesiones revocadas y eliminacion de cuentas

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
  directo por RLS y la consulta privada debe indicar sesion inactiva.
- Controles positivos de sesiones vigentes, aislamiento entre usuarios,
  `not_after`, suspension, eliminacion logica y eliminacion por Auth Admin.
- Las pruebas destructivas se limitan a cuentas sinteticas en localhost.

## Limites que siguen abiertos

Esto no es el ejecutor de eliminacion integral de cuentas. El centro de
privacidad registra solicitudes y respuestas, pero todavia no borra toda la
cuenta automaticamente. No se ha eliminado ningun cliente real.

Una peticion ya autorizada y en curso no se cancela retroactivamente. Una URL
firmada de Storage ya emitida puede funcionar hasta su vencimiento (actualmente
cinco minutos), salvo que se elimine antes el objeto. El ejecutor de borrado
debera detener trabajos, eliminar originales y derivados, comprobar remanentes,
purgar caches y documentar las excepciones de conservacion y los respaldos.

El proveedor confirma que eliminar `auth.users` no invalida por si solo los JWT
emitidos: https://supabase.com/docs/guides/auth/managing-user-data
