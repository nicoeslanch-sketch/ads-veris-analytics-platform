# Preparacion comercial: seguridad, costos y decisiones

## Decisiones confirmadas

- Repositorio publico, por decision del propietario. No se cambia a privado.
- Una cuenta por PYME al comienzo. Equipos con roles en una fase posterior.
- Pasarela elegida: Transbank. Cobros reales deshabilitados.
- Priorizar mejoras sin contratar infraestructura. No se compro ni amplio un plan.

## Evaluacion critica del consejo externo

| Consejo | Decision y alcance |
| --- | --- |
| Repositorio privado | No ahora, por decision expresa. Ser publico no sustituye ni invalida la seguridad. Secret scanning y push protection estaban habilitados; no habia alertas abiertas reportadas. Eso no certifica ausencia de secretos en todo el historial. |
| Proteger main | Aplicado: PR obligatorio, checks API/frontend/E2E/dependencias y laboratorio PostgreSQL, rama actualizada, sin force push ni borrado, administradores incluidos. Cero aprobaciones de terceros obligatorias mientras exista un solo mantenedor. Dependabot alerts y actualizaciones de seguridad habilitados; no se fusionan automaticamente. |
| Ownership con service_role | Confirmado en el enlace Google Sheets. UUID y comprobacion de propietario en backend, mas FK compuesta dataset/propietario en PostgreSQL. La consulta de diagnostico en produccion no encontro enlaces cruzados existentes. No se asume que todo uso de service_role haya quedado centralizado. |
| Cuotas IA atomicas | Reserva en PostgreSQL previa al proveedor. Cupo mensual, addon y limite de 12 intentos/minuto compartidos entre replicas. Fail-closed. SDK sin retries automaticos. |
| Auditoria administrativa | Planes, creditos, Coins y soporte se modifican junto con su auditoria en una transaccion. Se revoca al backend la reescritura/borrado del historial de auditoria y del ledger de Coins. |
| Bypass por correo | Eliminado de admin, contexto de acceso y consolidacion. Se comprobo primero que el administrador designado tiene is_admin en la base. Se conserva el mecanismo de bootstrap de la migracion 0018; revisar su gobierno antes de admitir mas administradores. |
| Limites distribuidos | Implementado para admision de IA/limpieza dirigida, ademas de cuotas y cola ya existentes. Aun no se han sustituido todos los limitadores locales de soporte/trial por un limitador global. |
| Organizations | No migrar masivamente ahora. No compartir contrasenas para simular equipos. Antes de lanzar equipos: memberships, invitaciones, roles, propiedad y migracion probada. |
| Archivos grandes | Extraidos limites de formatos, acceso a datasets, RPC comerciales y observabilidad. No se reescribe el motor ni se cambia su semantica para reducir lineas. |
| Observabilidad | Identificador de solicitud generado por servidor, cabecera X-Request-ID y logs de errores/solicitudes lentas con duracion y ruta parametrizada. No equivale todavia a APM, alarmas ni trazas distribuidas completas. |
| Cabeceras web | CSP permite scripts propios y conexiones solo a la API/Supabase actuales, bloquea iframes externos del sitio, objetos y formularios a terceros. Nosniff y Permissions-Policy. Antes de integrar el formulario de Transbank, anadir solo sus origenes oficiales necesarios y probarlos; no ampliar a comodines. |
| Formatos | Subida y loader comparten .xlsx/.csv. .xls/.tsv/.txt se rechazan antes de almacenarse en lugar de prometer un procesamiento inexistente. TSV puede convertirse a CSV; soporte nativo futuro requiere pruebas propias. |
| Docker/API Gateway/MCP | No son necesarios para cerrar estos riesgos ni para este lanzamiento. Docker se usa solo en CI para una base desechable, no se agrega infraestructura permanente. |
| Backups | Snapshots analiticos NO son respaldo de desastre. Sigue pendiente un respaldo verificable de PostgreSQL y objetos Storage, con restauracion ensayada y responsable operativo. |

## Cuotas y fallos de proveedor

Cada intento tiene una reserva durable antes de llamar a IA. Una respuesta correcta confirma la reserva. Un fallo local de limpieza reintegra su reserva/addon de manera idempotente.

Un timeout o una desconexion de IA no demuestra que el proveedor no haya procesado/cobrado. Por seguridad, conserva la reserva y requiere conciliacion antes de reintegrarla. No hay liberacion automatica por TTL que permita repetir llamadas caras gratuitamente. Si el proceso cae despues de reservar y antes de llamar, tambien puede quedar pendiente. Hace falta una pantalla/proceso operativo de conciliacion antes de vender consumo de IA; el chat avanzado sigue deshabilitado.

Los controles de cuota son PostgreSQL, no un nuevo Redis de pago. Las consultas informativas no autorizan consumo. El saldo de addons se suma en la base, sin depender del limite de filas de PostgREST.

## ADS Coins

- Son creditos de servicio, no moneda, criptomoneda, deposito ni saldo retirable.
- Asignacion mensual vigente: Basico 100, Analista 500, Gold 1200; administrador 2500. No se inventa una equivalencia en CLP.
- Costo proyectado actual: 5 Coins por respuesta avanzada. Equivalencias proyectadas: 20, 100 y 240 respuestas por asignacion de plan, respectivamente. El costo real depende de la configuracion del servidor; no hay cobro activo.
- La billetera muestra saldo disponible y respuestas proyectadas. Un saldo no verificable se muestra como no disponible, no como cero confirmado.
- Al subir de Basico a Analista durante el mismo mes, se otorgan 400 adicionales, no otros 500. Bajar y volver a subir no concede nuevamente la asignacion. Las concesiones historicas ya emitidas no se confiscan.
- Una operacion repetida con el mismo ID no duplica creditos; un ID reutilizado con otro contenido se rechaza. El panel conserva el ID tras una respuesta incierta mientras permanece montado. Tras recargar la pagina, revisar el historial antes de repetir un otorgamiento.

Antes de vender paquetes: aprobar precio CLP, margen con costos reales del proveedor, impuestos, politica de devoluciones, expiracion/no expiracion y terminos. No se debe vender una funcion marcada como proximamente ni presentar un costo proyectado como tarifa contratada.

## Transbank: ruta de implementacion

Webpay Plus sirve para pagos puntuales. Para una suscripcion con cargos posteriores, evaluar Oneclick (inscripcion de tarjeta y autorizaciones posteriores; ADS Veris programa periodos/reintentos) frente a PatPass (producto de cobro recurrente administrado por Transbank). No son transferencias bancarias. Confirmar disponibilidad/contrato/comisiones con Transbank; no afirmar que Webpay Plus activa por si solo una mensualidad automatica.

Fuentes oficiales consultadas el 21-09-2026:
- https://transbankdevelopers.com/producto/webpay
- https://publico.transbank.cl/productos-y-servicios/soluciones-para-ventas-internet/webpay-patpass
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches

Secuencia requerida antes de cobrar:
1. Cuenta de comercio y producto de recurrencia confirmados; precios y condiciones aprobados.
2. Checkout/inscripcion alojados por Transbank. ADS Veris no recibe PAN, CVV ni contrasenas bancarias. Tokens de recurrencia son secretos revocables, nunca datos de tarjeta en el navegador o logs.
3. Catalogo/precios en servidor; orden propia vinculada a cuenta, periodo, moneda y total. El navegador no determina importe ni plan concedido.
4. Confirmacion servidor a servidor. Un retorno del navegador no activa un plan. Verificar comercio, orden, estado final, monto y ambiente; confirmacion y derechos en una transaccion idempotente.
5. Estados para cancelado, rechazado, pendiente, autorizado y reembolso. Un timeout es pendiente de conciliacion, no permiso para cobrar otra vez.
6. Mandato explicito, proxima fecha y monto, cancelacion accesible, manejo de cambios de plan, periodos y reintentos acotados. Nunca cobrar despues de una cancelacion efectiva.
7. Pruebas sandbox completas, conciliacion y simulacion de callbacks repetidos/perdidos antes de produccion. No existe todavia una integracion de cobro lista para activar con una bandera.

## Validacion y limites de la evidencia

- Nuevo workflow `Commercial security`: Supabase/PostgreSQL/Auth/REST desechables en loopback, sin secretos de produccion ni archivos de clientes. Pruebas reales de FK, RLS, permisos RPC, cuotas concurrentes, replay, reintegros, auditoria fallida y cambios de plan/Coins.
- Pruebas HTTP locales aseguran que una reserva rechazada no llama al proveedor, un archivo ajeno no se vincula y un correo no sustituye el rol de base.
- Reprocesado local del libro multioja suministrado: 16 hojas sin error de estandarizacion/limpieza; filas y procedencia conservadas; exportacion de 15 hojas de datos mas auxiliares; tres totales anuales de ventas reconciliados con suma independiente de celdas exportadas. Artefactos privados en `artifacts/`, no publicados en el repositorio.
- Los duplicados se conservan por decision del usuario. Tras normalizar, algunas filas distintas en formato resultan iguales: eso no es perdida de filas ni permiso para borrarlas. No se certifica equivalencia universal con Power Query para cualquier archivo posible.
- Playwright local con el libro real: aprobado, Resumen/Explorar, seleccion de hoja, totales y desbordes desktop/mobile. Exportacion 28,719 s en este equipo; no es una promesa de latencia en Render. Pruebas locales: 1157 backend y 195 frontend; compilacion de produccion aprobada.
- Actualizado Vitest a 4.1.11 para corregir GHSA-82fw-gwwq-j7x9 (Vitest y @vitest/mocker). El alcance publicado es el servidor de desarrollo/pruebas, no el frontend estatico desplegado. Auditoria npm: cero vulnerabilidades conocidas tras actualizar. Fuente: https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9
- Laboratorio PostgreSQL ampliado aprobado: run 35674005485, 16 comprobaciones de seguridad. La evidencia usa el SHA de merge sintetico de GitHub, no un despliegue productivo.

Supabase Security Advisor (21-09-2026) informa MFA insuficiente y proteccion de contrasenas filtradas deshabilitada. No se desactivan advertencias ni se contrata un plan para ocultarlas. La funcion `can_process_data()` es SECURITY DEFINER intencionalmente para las politicas comerciales, devuelve solo un booleano del usuario autenticado; merece seguimiento, no revocar su acceso sin sustituir esas politicas. Las seis tablas sin politicas de lectura de clientes son deliberadamente backend-only.

Referencias de esos pendientes:
- https://supabase.com/docs/guides/auth/auth-mfa
- https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection
- https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable

## Bloqueadores de lanzamiento comercial

No se declara la plataforma invulnerable ni con capacidad certificada. Pendientes: pagos/suscripciones sandbox y conciliacion, MFA para administradores, respaldo/restauracion real, alertas operativas, limite distribuido de las restantes rutas sensibles, prueba sostenida representativa del plan de infraestructura elegido, condiciones comerciales y tratamiento de datos. Estos no se resuelven prometiendo mas usuarios por contratar un plan.

La arquitectura actual con workers y cuotas es reutilizable. Primero medir CPU/memoria/colas con archivos representativos; aumentar recursos solo cuando las mediciones lo justifiquen. Referencia de capacidad aislada y presupuesto condicional: `CAPACIDAD_LAB_2026_09_15.md` y `PRESUPUESTO_ESCALADO_2026_09_15.md`.
