# Explorar, seguridad y bases de capacidad

## Alcance y estado

Esta entrega reduce texto en Explorar, introduce evidencia de inactividad por ID,
y aplica una cuota central de Storage mediante subidas controladas.
No certifica usuarios simultaneos ni convierte todavia el pipeline clasico en
una cola durable con workers independientes. No se contrato ningun plan.

Explorar conserva dos visualizaciones cuando las variables existen: evolucion y
comparacion de grupos, con selector de medida/desglose y orden mayor/menor.
Hasta tres sugerencias breves; calidad, relaciones y evidencia quedan plegadas.
Los rankings de ingresos no se llaman unidades vendidas ni rentabilidad.

La actividad de productos se calcula desde IDs explicitos y ventas positivas,
no desde la ausencia en un top-N. Requiere tres meses consecutivos sin marca de
cobertura parcial; excluye IDs con ventas positivas sin fecha. Son ventas no
observadas en el archivo y filtros, no prueba de ausencia de demanda. Sugiere
contrastar stock, estacionalidad, precios, costos y marketing antes de decidir.

## Cuotas y despliegue seguro

`20260914093659_storage_capacity_reservations` crea contabilidad privada y RPC
solo para `service_role`. Un bloqueo corto de una fila coordina reservas entre
instancias. Cuenta todos los objetos del bucket, incluidos derivados, y bytes
reservados no materializados. No modifica tablas internas de Storage.

| Cuenta | Originales | Originales y derivados |
| --- | ---: | ---: |
| Basico / prueba | 10 | 100 MiB |
| Analista | 25 | 250 MiB |
| Gold / administracion | 50 | 500 MiB |

Presupuesto inicial global: **750 MiB**, un techo de operacion elegido para el
piloto, NO el espacio contratado ni capacidad vendida a todos simultaneamente.
Las cuotas por cuenta no garantizan que el proyecto tenga ese espacio libre;
manda primero el limite global. La revision inicial observo 73 objetos y
58.316.692 bytes, sin leer contenido privado ni borrar archivos.

`POST /storage/upload` verifica sesion, plan, tamano real y formato, genera la
ruta con la identidad autenticada y transmite en bloques de 64 KiB. Dos subidas
activas por proceso; las adicionales reciben 429 antes del parser. El flujo
clasico conserva su limite de 15 MiB. Los escritores de cache y consolidacion
tambien reservan antes de guardar. No hay excepcion de cuota para administradores.
Las lecturas y descargas de objetos existentes no consumen nueva cuota.

Si guardar cache no cabe, la limpieza/exportacion calculada sigue disponible en
memoria por el camino existente; no se altera la limpieza para ahorrar espacio.
Una nueva fuente rechazada por cuota muestra 507 y pide liberar archivos desde
Historial. Configuracion muestra uso, cupo y reservas. La subida agrega un salto
de red a Render, sin procesar pandas ni cargar todo el archivo en RAM; es un
compromiso explicito de seguridad. Para volumen alto, conviene un servicio de
ingesta dedicado con cuotas equivalentes, no reabrir escrituras directas libres.

Ante timeout remoto ambiguo se conserva la reserva. No caduca automaticamente:
el objeto podria haberse guardado aunque su confirmacion se haya perdido. Esto
evita exceder cuota, pero puede requerir reconciliacion operativa. Los errores
4xx definitivos liberan la reserva y el exito la liquida cuando el objeto ya
refleja el tamano esperado. No borrar reservas inciertas por antiguedad sin
comprobar que no existe una escritura pendiente.

Orden de activacion: migracion de reservas; API nueva y comprobacion; frontend
con subida gestionada; cierre de INSERT/UPDATE directo al bucket mediante una
segunda migracion. Ambas fases estan aplicadas; la segunda es
`20260915004403_require_managed_storage_uploads` (fecha UTC). Se verificaron sus
politicas RESTRICTIVE para authenticated y se conservaron las politicas de lectura.
No cerrar la politica antes de que ambos despliegues esten listos.
Las pestañas antiguas requieren recarga para usar la nueva ruta de subida.
La consolidacion experimental de mas de 15 MiB queda fuera de este camino y
requiere ingesta y worker dedicados; no se habilito en produccion.

## Seguridad comprobada y limites

Pruebas sinteticas locales: autenticacion, claims falsos, traversal, SSRF,
limites de cuerpo, expansion XLSX, formulas exportadas y admision de trabajo.
Pruebas SQL contra permisos reales, dentro de transacciones revertidas:
una cuenta normal no puede leer datasets/objetos ajenos, actualizar `is_admin`
ni llamar RPC de reservas. Se comprobo reserva duplicada, contabilizacion,
rechazo de presupuesto global y conservacion de una reserva sin objeto confirmado.
No se ejecuto DoS en produccion ni se extrajeron datos bancarios de archivos.

Las 27 tablas publicas observadas tienen RLS. Los RPC nuevos son SECURITY
INVOKER y no ejecutables por anon/authenticated. El advisor mantiene avisos
por MFA y contrasenas filtradas. `can_process_data()` sigue siendo una funcion
de autorizacion intencional sobre la propia identidad. Tablas internas sin
politicas cliente estan cerradas, no hay que abrirlas para silenciar el advisor.

Pendientes: MFA de extremo a extremo (alta, desafio, recuperacion y enforcement),
proteccion contra contrasenas filtradas, rate limits distribuidos y defensa de
borde, alertas operativas y restauracion comprobada de backups. La cuota nueva
cubre objetos Storage, NO todos los bytes de tablas, snapshots JSON, logs,
transferencia o facturacion de proveedores. Un pentest independiente sigue siendo
recomendable antes de tratar informacion especialmente sensible a gran escala.

La verificacion en la sesion de produccion mostro la cuota (46,1/500 MiB,
9/50 originales) y el analisis del libro PYME con las tres hojas de ventas y
costos conectados por SKU. El primer calculo aun tardo varios minutos: esta
entrega no declara resuelta la latencia de procesamiento. El bot se probo con
preguntas de inactividad y seguimiento; se corrigio una repeticion cuando no
habia evidencia temporal suficiente, conservando la distincion entre guia
general y diagnostico de un producto concreto. Tambien se corrigio la pregunta
real `cuantosarchivospuedoguardar` y se anadieron nueve variantes de cuota,
palabras unidas y errores de escritura como regresiones.

Pruebas de la entrega: suite backend previa de 1.013 casos aprobados, mas cuatro
regresiones del seguimiento conversacional y nueve de escritura; frontend 186 aprobados y flujo
Playwright 19 aprobados / 1 omitido (libro real opcional). El ultimo cambio de
version/cuotas se comprobo con 30 casos y la suite conversacional con 104.
Avisos pendientes del advisor:
[MFA](https://supabase.com/docs/guides/auth/auth-mfa) y
[proteccion de contrasenas filtradas](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).

## De que depende la capacidad

- Vercel sirve la interfaz; abrir una pagina ya cargada no ocupa un worker pandas.
- Render aporta CPU/RAM al backend. Procesar Excel y unir hojas consume ambas.
- Supabase aporta autenticacion, base de datos y Storage; sus conexiones, espacio
  y transferencia tambien limitan la operacion.
- El codigo determina cache, cola, equidad entre cuentas, cantidad de workers,
  reintentos y recuperacion tras reinicios. Mas RAM no corrige por si sola una
  cola local ni crea paralelismo que el codigo no habilita.

Estado actual: un calculo pesado a la vez por proceso. La cola de analisis
clasica conserva funciones locales; Redis opcional no la hace durable. Aumentar
workers Uvicorn sin separar trabajos multiplicaria caches y memoria. El worker
de consolidacion existente no procesa automaticamente los jobs del flujo clasico.

### Precios oficiales consultados el 14 de septiembre de 2026

| Compute Render, por servicio | RAM | CPU | USD/mes | Uso razonable |
| --- | ---: | ---: | ---: | --- |
| Free | 512 MB | compartida | 0 | Desarrollo y piloto restringido |
| 0.5c-512mb, antes Starter | 512 MB | 0,5 | 7 | API ligera; poca RAM para Excel complejos |
| 1c-2g, antes Standard | 2 GB | 1 | 25 | Primer worker aislado de procesamiento |
| 2c-4g, antes Pro | 4 GB | 2 | 85 | Mayor carga, tras medir RAM y concurrencia |
| 4c-8g, antes Pro Plus | 8 GB | 4 | 175 | Escala posterior, no necesaria sin mediciones |

[Precios de compute](https://render.com/pricing) y
[nombres actuales de planes](https://render.com/docs/compute-plans).
Son por servicio; no incluyen otros proveedores, impuestos ni excesos de uso.
El workspace Hobby cuesta 0, Pro 25 y Scale 499 USD/mes, separado de compute.
Comprar workspace Pro no incrementa la RAM de la API.
[Planes de workspace](https://render.com/blog/better-pricing-for-fast-growing-teams).

Propuesta inicial, sujeta a aprobacion: API ligera de 7 USD mas worker de 2 GB
por 25 USD = **32 USD/mes de compute**; API de 2 GB mas worker de 2 GB = 50 USD
si las mediciones lo aconsejan. Supabase/Vercel/workspace/transferencia van aparte.
La separacion API/worker aun exige completar la cola durable antes de activarla.
[Funcion de los background workers](https://render.com/docs/background-workers).

No existe una equivalencia fija plan/personas. Modelo ilustrativo, NO benchmark:
con un worker, trabajo medio de 30-120 segundos y uso objetivo de CPU del 60%,
la capacidad seria 18-72 trabajos por hora. A dos trabajos por usuario/hora,
equivale a 9-36 usuarios generando esa carga; no usuarios navegando ni registrados.
Dos workers: 36-144 trabajos/hora, solo si RAM/DB y el trabajo permiten escalar.
La formula es `workers * 3600 / segundos_por_trabajo * 0,60`.

### Siguiente implementacion necesaria

1. Cola durable para estandarizacion, limpieza, metricas y exportacion, con
   referencias a fuentes propias y opciones versionadas, nunca closures/pickle.
2. Worker independiente con lease, heartbeat, cancelacion, reintentos acotados e
   idempotencia. Reutilizar las convenciones de la consolidacion existente.
3. Admision atomica global/por cuenta, colas justas y presupuestos de CPU/RAM;
   cache compartida sin recalcular simultaneamente la misma identidad.
4. Staging aislado con CSV/XLSX pequeno, mediano y multihoja; medir p50/p95,
   espera de cola, RSS pico, errores y costo con 5/10/25/50 sesiones sinteticas.
5. Aumentar instancias solo tras fijar objetivos medibles y aprobar presupuesto.

La documentacion anterior de septiembre describe la situacion previa de
retencion blanda. Este documento y las migraciones nuevas describen el cambio;
no suponen que el resto de pendientes se haya resuelto.
