# Presupuesto minimo para un piloto comercial

Referencia: 15 de septiembre de 2026. Precios en USD/mes, antes de impuestos,
consumos extra y conversion a CLP. Es una propuesta, no una compra ni una
certificacion. No se consulto la facturacion privada de las cuentas: el costo
incremental depende de los planes que ya esten contratados.

## Propuesta de menor costo manteniendo Vercel

| Componente | Candidato inicial | Base mensual |
| --- | --- | ---: |
| API Render | 0.5 CPU / 512 MB, antes Starter | 7 |
| Procesador Render separado | 1 CPU / 2 GB, antes Standard | 25 |
| Supabase | Pro, un proyecto Micro incluido | 25 |
| Frontend Vercel | Pro, un desarrollador | 20 |
| Total de componentes | Sin extras ni workspace Render de pago | 77 |

Los recursos y tarifas de API/worker proceden de
[Render](https://render.com/pricing). Los nombres antiguos siguen admitidos en
[BluePrints y API](https://render.com/docs/compute-plans).

[Supabase Pro](https://supabase.com/pricing) parte de USD 25 con el primer
proyecto Micro; otro proyecto Micro permanente de staging suma aproximadamente
USD 10/mes. [Vercel Pro](https://vercel.com/pricing) parte de USD 20:
Hobby esta reservado para uso personal no comercial.

**La API de 512 MB es un candidato sujeto a pruebas, no una recomendacion
incondicional.** Aun existen rutas sincronicas/compatibilidad que pueden cargar
datos. Si los flujos representativos superan 350 MiB sostenidos o provocan OOM,
subir API a 1 CPU / 2 GB agrega USD 18: base de componentes USD 95/mes.
No rebajar un plan existente hasta medir esos flujos y el margen de memoria.

El workspace Render Hobby cuesta USD 0, con limites de colaboradores y servicio;
el workspace Pro agrega USD 25/mes. Elegirlo segun permisos y necesidades del
equipo, no confundirlo con el plan de computo de cada servicio.
[Precios actuales del workspace](https://render.com/blog/better-pricing-for-fast-growing-teams).
Asi, la base con workspace Pro seria USD 102 o USD 120, respectivamente.

No incluye dominio, correo transaccional, copia externa de archivos, excedentes
de transferencia, builds, herramientas de monitoreo ni proveedor de IA avanzada.
Son bases de calculo, no un techo de la factura. Mantener los topes de consumo
disponibles y alertas. No comprar Redis en esta etapa: la cola ya usa PostgreSQL.

Como alternativa futura, Render ofrece hosting estatico sin costo de computo,
lo que podria eliminar el cargo de Vercel. No se propone migrar ahora sin medir
su impacto y revisar dominios, CORS, autenticacion y protecciones del despliegue.

## Que determina la capacidad

- Navegar o leer un resultado ya calculado consume principalmente API, base de
  datos y red. No es equivalente a volver a procesar un libro completo.
- Limpiar, relacionar hojas y calcular por primera vez consume CPU y RAM del
  procesador. Tamano comprimido no equivale a memoria necesaria.
- La cantidad de archivos depende del volumen real, caches, resultados,
  retencion, copias y cuotas; no solo del numero de cuentas registradas.
- Un cliente con muchos libros grandes puede consumir mas que muchos clientes
  que consultan resultados existentes. MAU de un proveedor no significa usuarios
  simultaneos calculando en esta aplicacion.

Para planificar: si un proceso representativo tarda T segundos y hay W plazas
de ejecucion, el maximo teorico es 60*W/T trabajos/minuto. Trabajar inicialmente
por debajo del 60-70% de ese maximo es un margen de planificacion, no un SLA.
Colas, variacion de archivos, red y reintentos reducen el rendimiento real.

Actualmente el limite de cola es 32 activos globales, 3 por cuenta y 1 calculando.
Esos limites protegen recursos; no dicen que haya 32 clientes soportados.
La cuota global de archivos sigue en 750 MiB y no se amplia automaticamente al
contratar Supabase Pro. Por ejemplo, 750 MiB / 5 MiB son 150 originales teoricos
antes de reservar espacio para derivados, caches y otras cuentas.

## Orden de activacion, solo tras aprobar el gasto

1. Completar laboratorio aislado y guardar evidencia reproducible.
2. Preparar staging con Supabase distinto, sin claves ni archivos de produccion.
3. Usar el blueprint `deploy/render-analysis-worker.yaml` con credenciales del
   entorno correcto. Mantener limite global 1 mientras se mide memoria.
4. Probar XLSX multihoja, CSV, subida, limpieza y descarga con tamanos reales,
   ciclos frios/calientes y una carga mas larga que el smoke de GitHub.
5. Activar consumidor externo en produccion, verificar version, aislamiento,
   fallos y descarga antes de admitir clientes adicionales. No aumentar el
   limite global a dos hasta aprobar otra medicion.
6. Ajustar cuotas segun margen total disponible, retencion y alertas; comprobar
   MFA administrativo y restauracion de base y objetos en entorno separado.

Las [copias de la base de Supabase](https://supabase.com/docs/guides/platform/backups)
no incluyen los bytes de Storage. Pro no reemplaza un respaldo de los Excel ni
una prueba de restauracion de esos archivos.

## Reversibilidad

Si el worker externo falla, las tareas quedan en PostgreSQL y pueden recuperarse
al vencer su lease. Para volver al modo anterior, devolver la API a `embedded`
y detener el worker externo. Mantener el limite global de uno durante todo el
cambio y validar las tareas en curso. No borrar la cola ni los archivos.
