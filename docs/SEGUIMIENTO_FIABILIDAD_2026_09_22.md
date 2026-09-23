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
  integridad y rechazo de respaldos parciales. Restauracion todavia en correccion.
  Pendiente destino confirmado y copia real de produccion. No hay copia de
  clientes publicada ni subida a GitHub.
- Alertas: contador agregado acotado, latidos privados, umbrales y panel admin
  implementados; 17 pruebas locales pasan. Pendiente validacion SQL en laboratorio,
  despliegue y destino de notificaciones externas. No sustituye monitor externo.
- Pendiente: prueba sostenida representativa y mediciones.
- Pendiente: ampliar casos de limpieza, uniones y dialogos, requisitos comerciales.
- Pendiente: propuestas diferenciadas Basico/Analista/Gold, sin publicar precios.
- Pendiente al finalizar lo anterior: Caso_PYME_Datos_Sucios.xlsx contra
  Control_Validacion_Caso_PYME.xlsx. El control no se sube a la plataforma.

No confundir implementado, probado localmente, probado en laboratorio y
desplegado. No se certifica una capacidad de usuarios hasta medir la configuracion
y carga concretas. No se afirma que limpieza general pueda reconstruir valores
originales que ya no existen en las fuentes.
