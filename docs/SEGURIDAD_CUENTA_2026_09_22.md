# Seguridad de cuenta y preparacion comercial

## Alcance de esta entrega

- Segundo factor TOTP en Configuracion, con enrolamiento explicito, confirmacion,
  retiro y autenticador de respaldo. QR y clave solo en memoria de la pantalla,
  nunca guardados por ADS Veris ni enviados a sus logs.
- Administradores: segundo factor obligatorio en produccion. Clientes: opcional;
  al verificar un factor pasa a ser obligatorio para acceder a datos.
- API verifica JWT antes de evaluar AAL. No confia en user_metadata. Un endpoint
  de configuracion de primer factor devuelve solo booleanos de la propia cuenta.
- Politicas restrictivas adicionales en todas las tablas public con RLS y en
  storage.objects. Se conservan las politicas de propiedad y las cuotas existentes.
- Ventanas atomicas compartidas en PostgreSQL: trial y facturacion (5 intentos
  en 10 minutos), solicitudes de soporte (5 en 10 minutos), chat (12 por minuto).
  Sin Redis adicional. Fallo de verificacion bloquea la escritura; no se inventa saldo.
- Soporte: tope de tres pendientes y rechazo de duplicados en una transaccion,
  incluso con solicitudes simultaneas. El hash de los buckets evita guardar RUT
  en texto en el limitador; no convierte un identificador predecible en anonimo.
- Administracion incorpora un estado comercial bajo demanda, sin nuevos llamados
  al abrir Resumen. Distingue configuracion, preparacion, verificacion y pendientes.
- Compras siguen desactivadas. Un flag aislado no puede habilitar checkout:
  produccion rechaza una configuracion que intente activarlo sin integracion.

## Operacion del doble factor

En el siguiente ingreso del administrador, la pantalla pide configurar el
autenticador. El titular debe escanear personalmente el QR y escribir su codigo.
No debe enviar QR, clave manual, contrasena o codigo a soporte ni a un asistente.
Conviene agregar un segundo dispositivo desde Configuracion despues de ingresar.

Si se pierde un autenticador, usar el segundo y retirar el perdido. No hay un
boton que quite MFA por conocer el correo o cambiar la contrasena. Sin respaldo,
el responsable de seguridad debe verificar identidad fuera de esa sesion,
registrar el incidente, revocar sesiones y gestionar el factor desde Supabase.
No eliminar el rol administrador ni desactivar RLS para recuperar acceso.
Una vez retirados los factores, el administrador vuelve a enrolar antes de entrar.

Los JWT AAL2 ya emitidos pueden seguir vigentes hasta expirar; retirar un factor
no equivale a revocar inmediatamente todos los tokens firmados. Ante robo de
sesion, revocar sesiones, evaluar rotacion y seguir el procedimiento de incidente.
El proyecto aun no tiene un servicio de respuesta a incidentes 24/7.

## Despliegue

Aplicar migraciones solo despues de aprobar el laboratorio desechable.
La migracion MFA afecta acceso directo a datos inmediatamente: coordinar con
el despliegue del frontend y API, avisando al administrador. No enrolar cuentas
reales con herramientas automatizadas. Verificar /version y el formulario sin
capturar un QR real. Mantener compras desactivadas en todos los ambientes.

## Evidencia requerida

- pytest: contratos HTTP, autorizacion, errores cerrados y regresiones del motor.
- Vitest: formato del codigo y parseo estricto del estado, errores sin diagnosticos.
- Playwright: interfaz sinteticamente aislada, codigo incorrecto, confirmacion,
  bloqueo del ultimo factor administrador y medidas desktop/mobile.
- Supabase local desechable en CI: Auth real, desafio TOTP, AAL1/AAL2, aislamiento,
  todas las tablas RLS y Storage, carreras de ventanas y solicitudes de soporte.
- Ninguna prueba de carga ni extraccion de datos se realiza sobre clientes reales.

## Lo que no se da por terminado

No hay integracion de pagos ni suscripciones, ni promesa de activacion comercial
con un clic. Faltan precios finales, condiciones, aprobacion del comercio y
pruebas de conciliacion. El usuario ha pedido posponer esa integracion.

Siguen pendientes respaldo externo de PostgreSQL y objetos Storage con prueba
de restauracion, alertas operativas, conciliacion de reservas IA inciertas y
certificacion de capacidad sostenida. Tampoco se afirma que todos los endpoints
sean ahora globalmente rate-limited o que sea imposible comprometer el sistema.

No se cambio el motor de limpieza, estandarizacion, graficos o bot en esta
entrega. Su suite de regresion se conserva; esto no equivale a volver a auditar
todos los archivos posibles ni a certificar equivalencia universal con Power Query.
