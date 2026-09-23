# Fiabilidad y preparacion comercial

Solicitud: reparar relaciones y presentacion primero; luego recuperacion,
operaciones, capacidad, rendimiento, validacion, bot, requisitos comerciales y
comparacion de los dos Excel de PYME. Pagos apagados; sin compras autorizadas.

## Estado de esta etapa (trabajo en curso)

- Verificado en CI (Playwright, tipos y build): conclusiones en Explorar y numeros de relaciones
  sin cortes, moneda UF explicita, etiquetas legibles.
- Implementado y probado localmente/CI: relaciones en la cola durable existente, sin
  calculo generico duplicado en Explorar; contexto propio del bot por conexion.
- Confirmado en codigo/pruebas previas: MFA obligatorio para administradores;
  clientes sin factor voluntario acceden con correo/contrasena. El titular
  confirmo que completo su autenticador y accedio a la plataforma.
- Respaldo: herramientas cifradas implementadas; laboratorio verifico cifrado,
  integridad, rechazo de respaldos parciales, restauracion de datos/Auth/Storage,
  ownership y descarga autenticada. Runs 35844587521 y 35846417096 aprobados.
  Pendiente destino confirmado y copia real de produccion. No hay copia de
  clientes publicada ni subida a GitHub.
- Alertas: contador agregado acotado, latidos privados, umbrales y panel admin
  implementados y verificados en PostgreSQL y navegador. Monitor publico GitHub
  preparado para detectar caidas sin datos de clientes. Pendiente despliegue y
  comprobar recepcion de avisos. Saturacion interna sin canal externo aun.
- Capacidad: 435/435 analisis en 15 min con 5 cuentas, XLSX de 4 hojas y 4.000
  ventas, sin diferencias en los totales. Solo laboratorio aislado, no Render.
- Bot: conversacion de 20 turnos y regresiones de fechas, cifras, rankings,
  utilidad neta/bruta y cambios de conexion. Corregido relationship_id perdido
  al consolidar periodos. CI completo aprobado en 4b02054.
- Propuesta diferenciada Basico/Analista/Gold documentada, sin publicar precios
  ni cambiar permisos. Requisitos comerciales requieren decisiones del titular.
- Pendiente al finalizar lo anterior: Caso_PYME_Datos_Sucios.xlsx contra
  Control_Validacion_Caso_PYME.xlsx. El control no se sube a la plataforma.

No confundir implementado, probado localmente, probado en laboratorio y
desplegado. No se certifica una capacidad de usuarios hasta medir la configuracion
y carga concretas. No se afirma que limpieza general pueda reconstruir valores
originales que ya no existen en las fuentes.
