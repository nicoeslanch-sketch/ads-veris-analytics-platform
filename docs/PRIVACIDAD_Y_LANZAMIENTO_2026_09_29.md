# Privacidad y preparacion comercial

Responsable informado por el titular: ADS Veris SpA. Contacto: servicios@adsveris.com.
Version de los textos y aceptacion: 2026-09-28. Revision tecnica: 2026-09-29.
No es certificacion legal, de seguridad ni autorizacion para cobrar.

Migracion aplicada en produccion: 20260929094534_privacy_rights_and_consent.sql (version generada por Supabase al aplicar). Laboratorio PostgreSQL aprobado antes de aplicarla; no se borraron datos existentes.

## Implementado en este cambio

- Paginas publicas /privacidad, /condiciones y /licencias, accesibles sin login/MFA.
- Telefono opcional; consentimiento afirmativo en registro, sin publicidad ni casilla premarcada.
- Evidencia de version/fecha del servidor, inmutable para clientes. No se presume consentimiento antiguo.
- Antes de entrar al espacio de trabajo, la interfaz consulta esa evidencia. Si falta, presenta el texto y permite aceptar o ejercer derechos sin aceptar.
- Solicitudes de acceso, rectificacion, eliminacion y oposicion con comprobante durable, aislamiento por titular y una solicitud abierta por tipo. No requieren plan pagado.
- Bandeja administrativa y respuesta registrada junto con la auditoria en una transaccion.
- El boton de eliminacion completa SOLICITA la eliminacion. No ejecuta el borrado total de cuenta. Los archivos individuales se borran desde Historial con la saga existente.
- El bot explica esta diferencia y no simula haber borrado datos ni haber consultado una solicitud privada.
- Licencias completas de las dependencias de produccion en la distribucion. Poppins: OFL 1.1, local. Lucide: ISC/partes MIT. Victory omite su licencia raiz en npm; se conserva la del tag exacto y las de D3 incluido.
- Escaneo Gitleaks del historial y CI adicional. Tras incluir todas las ramas remotas, las dos coincidencias fueron TEST_SECRET en fixtures de tests; se excluyen SOLO sus huellas historicas exactas, no la carpeta tests. Sin otras coincidencias en los 259 commits revisados en ese punto; no es una garantia de ausencia absoluta de secretos.

## Registro interno de tratamientos (no inscripcion oficial)

| Actividad | Datos | Finalidad y acceso | Sistema | Conservacion actual / decision pendiente |
|---|---|---|---|---|
| Cuenta | Nombre, correo, empresa, pais, telefono opcional | Acceso y atencion; titular y administracion autorizada | Supabase Auth/profiles | Mientras la cuenta este vigente; falta procedimiento automatizado de cierre total |
| Prueba y contratacion | RUT, identidad enmascarada, plan y movimientos de creditos | Elegibilidad, antifraude, gestion comercial | Supabase | Definir plazos aplicables y supresion/limitacion posterior al cierre |
| Archivos y analisis | Contenido enviado, columnas, reglas, resultados | Limpieza y analisis por instruccion del cliente | Render, Supabase Storage/PostgreSQL | Cuotas por plan, poda al cargar; ultimos cinco exceptuados de antiguedad. No confundir con plazo maximo de toda la cuenta |
| Soporte | Preguntas, mensajes, respuestas | Ayuda y diagnostico | API y Supabase | Chat humano tiene caducidad; solicitudes durables no comparten necesariamente ese plazo |
| Derechos y aceptacion | Version, fecha, solicitud, respuesta, identificador de cuenta | Gestion de derechos y evidencia | Supabase | Revisar plazo minimo necesario y excepciones; no borrar una solicitud abierta por una poda de chat |
| Seguridad/operacion | Rutas, estado HTTP, latencia, identificadores tecnicos | Deteccion de fallos y abuso | Proveedores y monitor API | Verificar configuracion y retencion de cada proveedor; evitar contenido de archivos y secretos en logs |
| IA externa, si se habilita | Pregunta/contexto enviado | Respuesta avanzada | Anthropic | Revisar contrato y retencion del proveedor antes de activar para datos personales |

Para datos de terceros en archivos, el cliente debe determinar finalidad y base juridica; ADS Veris actua como encargado para ese procesamiento. Hace falta formalizar el contrato y subencargados, no basta esta tabla.

## Registro legal de bases de datos

El articulo 22 del texto vigente de la Ley 19.628 regula el registro de bancos de datos de organismos publicos. No se ha identificado una inscripcion general equivalente que corresponda automaticamente a este SaaS privado en Chile. NO se realizo ni se afirma una inscripcion oficial.

Fuentes revisadas:
- [Ley 19.628, BCN](https://www.bcn.cl/leychile/navegar?idNorma=141599&idVersion=2023-05-09).
- [Ley 21.719, BCN](https://www.bcn.cl/leychile/navegar?idNorma=1209272).
- [Propuesta de ampliacion de plazo, Ministerio de Economia, 01-09-2026](https://www.economia.gob.cl/2026/09/01/gobierno-propone-ampliar-plazo-para-implementar-nueva-ley-de-proteccion-de-datos-y-institucionalidad.htm). Una propuesta no equivale a ley vigente: volver a verificar antes del lanzamiento.

Falta confirmar todos los paises donde se ofrecera el servicio, el domicilio/RUT comercial y la revision profesional de textos, plazos, bases juridicas y transferencias internacionales. No publicarlos a partir de suposiciones.

## Criterios que siguen bloqueando la declaracion de lanzamiento completo

1. Ejecutar y verificar la eliminacion integral: Storage, filas, resultados y caches, trabajos en curso, sesiones/JWT, credenciales de conectores, backups y excepciones legales. Eliminar auth.users por si solo no invalida todos los JWT ya emitidos. No cerrar una solicitud sin evidencia.
2. Aprobar contratos de tratamiento, plazos de retencion efectivos y respuesta a incidentes. Comprobar el buzon de privacidad y asignar responsable de atenderlo.
3. Configurar destino externo de backups y probar restauracion de una copia real, sin exponer datos personales.
4. Medir capacidad en la infraestructura elegida. Las pruebas de laboratorio no certifican usuarios simultaneos de Render.
5. Completar validacion financiera pendiente (CxC, compras, indicadores cruzados); no anunciar exactitud universal ni equivalencia total con Power Query.
6. Aprobar precios, impuestos, condiciones comerciales, ADS Coins y facturacion. Pagos siguen apagados: faltan alta, integracion, pruebas y autorizacion de pasarela.
7. Confirmar licitud de los documentos financieros aportados para contenido del bot y titularidad de marca/favicon. No hay fotografias de stock en los recursos versionados revisados; esto no certifica futuros archivos del usuario.

No se necesita contratar Docker, MCP, un API Gateway ni microservicios para completar este bloque. Los servicios de pago finales se decidiran por necesidades verificadas, no como sustituto de estos pendientes.
