# Capacidad y persistencia: evidencia del 5 de octubre de 2026

## Resultado comprobado

La prueba aislada [37291238491](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/37291238491)
aprobo 150 analisis de cinco cuentas sinteticas durante una ventana de 300 segundos.
Cada cuenta utilizo un XLSX de cuatro hojas, con 4.000 transacciones y un catalogo.
Los importes se compararon con sumas independientes generadas antes del archivo.

| Medida | Resultado |
| --- | --- |
| Trabajos completados / enviados | 150 / 150 |
| Tiempo observado mediano | 2,832 s |
| Tiempo observado p95 | 4,486 s |
| Tiempo observado maximo | 6,804 s |
| Espera en cola p95 | 3,632 s |
| Procesamiento p95 | 0,833 s |
| Estandarizacion de cuatro hojas, mediana | 2,199 s |
| Limpieza de cuatro hojas, mediana | 1,686 s |
| Memoria RSS maxima del proceso API | 196,17 MiB |
| Memoria RSS maxima de cada proceso worker | 177,55 MiB |

El servidor del laboratorio tenia cuatro CPU y servicios locales. Los archivos
ya estaban preparados durante la fase sostenida; cada consulta cambiaba el filtro.
Hubo como maximo un trabajo en ejecucion, aunque participaron dos consumidores.
La carga ofrecida fue de una solicitud pendiente por cuenta, con al menos diez
segundos entre nuevos trabajos de la misma cuenta. No se busco saturar la cola.

Estas cifras describen esa prueba; no certifican usuarios simultaneos de Render,
tiempos de todos los Excel, capacidad de almacenamiento ni latencia por Internet.
La RSS tampoco incluye PostgreSQL, Storage u otros servicios del laboratorio.

## Recuperacion y seguridad comprobadas

- La cola sobrevivio al reinicio de la API y conservo la identidad del trabajo.
- Un worker interrumpido despues de adquirir el trabajo se recupero en el segundo
  intento, con el importe correcto, unos 123 segundos despues de la interrupcion.
  Ese plazo corresponde al vencimiento del lease; no es tiempo normal de calculo.
- Accesos sin sesion, accesos a trabajos ajenos y llamadas a la RPC privada desde
  una cuenta normal fueron rechazados.
- Se respetaron la cancelacion, el limite de admision por cuenta y el limite
  global de un trabajo pesado, incluso con dos consumidores.
- Se inyecto un fallo antes de escribir un snapshot y una respuesta perdida
  despues de escribirlo. Las cuatro hojas se guardaron correctamente.
- No hubo solicitudes a produccion ni lectura de archivos de clientes.

## Cambios de persistencia

`store_restore_snapshot` hace como maximo dos intentos con la misma revision
reservada y el mismo contenido. Los errores permanentes no se reintentan.
Ante una respuesta incierta, consulta exclusivamente el dataset y propietario
esperados, y confirma contenido, revision vigente y seleccion de hojas.
Las consultas de confirmacion tienen un plazo de cinco segundos.

El procedimiento conserva las RPC protegidas; no realiza escrituras directas ni
degrada a una funcion antigua. Una revision mas reciente o un contenido distinto
impiden confirmar el resultado anterior. Cuando se omiten las hojas excluidas,
se respeta la lista completa de hojas seleccionadas.

## Incidencia anterior y limites pendientes

La primera ejecucion [37253169244](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/37253169244)
se detuvo por un fallo parcial de persistencia. No registro el codigo concreto
de la base de datos, por lo que su causa original sigue sin determinarse.
La repeticion [37289629278](https://github.com/nicoeslanch-sketch/ads-veris-analytics-platform/actions/runs/37289629278)
aprobo 60 trabajos. El endurecimiento posterior se verifico mediante inyeccion
controlada; no se presenta como demostracion de la causa de aquella incidencia.
El laboratorio ahora conserva codigos de error y conteos, sin mensajes SQL,
credenciales ni contenido de las respuestas.

Para cerrar la validacion comercial todavia deben medirse cargas representativas
en la infraestructura objetivo y configurar respaldos externos con un ensayo de
restauracion operativo. En el modelo financiero quedan pendientes la conciliacion
empresarial de CxC, compras con detalle separado y todos los KPIs del control PYME.
Los pagos y el proveedor de IA avanzada continúan pendientes de activacion.
