# Calidad y seguridad - 2026-11-13

## Alcance

Revision local del motor, bot determinista e interfaz. Sin servicios contratados,
sin ataques a produccion, sin activar pagos ni IA de pago, sin borrar originales.
Las skills siguen instaladas en el equipo; no fue necesario reinstalarlas.
Base del cambio: `576fd8e`. Version del motor propuesta: `0.36.2` para invalidar
resultados anteriores a las correcciones numericas.

## Correcciones

- Numeros nativos de Excel conservan su escala: `1.239` numerico no se interpreta
  como `1239`. Las convenciones locales siguen aplicandose a texto.
- Valores como `1e309` no se publican como infinito: se mantienen en la fuente
  para revision y se excluyen de la suma numerica. No se eliminan filas.
- Booleanos en columnas mixtas se excluyen antes de la cache de valores unicos:
  `True` no puede convertirse en un importe de `1` por igualdad de claves Python.
- Cartera UF conserva fracciones pequenas. Sumatorias fuera de rango se presentan
  como no disponibles, con advertencia, en vez de cero/infinito o error de servidor.
- Bot: cantidad negativa/devuelta no se responde con unidades totales. Se distingue
  signo negativo de una devolucion confirmada; se informa detalle faltante.
- Ranking del bot: importe neto y participacion neta usan la misma base. Si solo
  existe participacion bruta, se explica por separado.
- Bot e interfaz preservan fracciones UF y centavos de moneda extranjera. Fracciones
  UF menores que la precision visible se expresan con un limite, nunca como cero.
- Formateadores `Intl.NumberFormat` reutilizados; valores no finitos no aparecen
  como KPIs validos. Panel de carga con mejor lectura por tecnologias de asistencia,
  foco visible, boton de cancelacion de 44 px y movimiento reducido.
- Admision previa a autenticacion: maximo configurable de 8 cuerpos HTTP en proceso
  por defecto y por proceso. Rechazo inmediato 429, liberacion al consumir el cuerpo
  y en cancelaciones/errores. No limita a 8 usuarios ni reemplaza controles globales.
- XML de libros procesado con `defusedxml==0.7.1`. Claves de cache de contenido
  migradas de SHA-1 a SHA-256; se evita recalcular el hash dentro del bucle de exportacion.

## Verificacion local

| Comprobacion | Resultado | Limite |
|---|---|---|
| Backend completo, estado final | 2323 pruebas pasan, 131 advertencias | Advertencias existentes; no todas las dependencias estan libres de deprecaciones |
| Frontend | 272 pruebas, 36 archivos pasan | No sustituye navegacion autenticada real |
| Build de produccion | TypeScript y Vite pasan | Publicacion se verifica por separado |
| Conversaciones del bot | 202 turnos, 0 fallos esperados | Datos sinteticos; no es una IA ni cobertura universal |
| Oraculo numerico nuevo | 5 movimientos: neto 600, costo 360, margen 240, unidades 60 | Incluye devolucion, categorias y mes incompleto |
| Hypothesis | 4 propiedades, hasta 900 ejemplos generados por ejecucion | Roundtrip, escala nativa, finitud, idempotencia de exportacion; ejemplos adicionales explicitos |
| Navegador, pase anterior del mismo cambio | 8 E2E pasan, escritorio/movil, relaciones/exportacion/exploracion | Antes del ultimo ajuste numerico; CI debe repetir el conjunto al publicar |
| Revision dimensional | 2 archivos, 13 funciones, 34 sondas | `receivables.py` y `format.ts`; no es auditoria dimensional de todo el motor |

El oraculo calcula sobre movimientos, no sobre una respuesta predeterminada del
bot. Febrero termina el dia 20 en ese caso: no se convierte en un mes completo para
forzar el resultado esperado. Se comprueban tambien cambio de dataset/moneda y soporte
humano. Las pruebas nuevas quedan en `api/tests/test_assistant_numeric_oracle.py`,
`test_assistant_return_quantities.py`, `test_numeric_properties.py`,
`test_request_admission.py`, `test_xml_and_cache_security.py` y las pruebas existentes
de cartera/formateo ampliadas.

## Escaneo estatico

Semgrep OSS 1.185.0, telemetria deshabilitada, analisis local de `api/app` y
`frontend/src`. Reglas aprobadas: security-audit, secrets, Python, FastAPI,
TypeScript, React y Trail of Bits. No se subio codigo a un servicio de analisis.

- API: 7 ejecuciones correctas; 102 archivos para reglas generales, 99 Python.
  React/TypeScript cubren cero archivos en este destino y no cuentan como cobertura.
- Frontend: 7 ejecuciones correctas; 161 archivos generales, 157 TypeScript/React.
  Python/FastAPI cubren cero archivos aqui y no cuentan como cobertura.
- Primer pase API: 5 hallazgos unicos (XML y cuatro usos SHA-1); corregidos.
  Pase posterior: 0 hallazgos. Frontend: 0 hallazgos. El ajuste final que excluye
  booleanos de `numeric_series` fue posterior a ese pase y tiene prueba de regresion.
- Ninguna ejecucion fallida u omitida en los manifiestos finales. Pro no disponible:
  el analisis no incluye su seguimiento entre archivos. 0xdea/Decurity no aplican a
  los lenguajes compatibles encontrados en este alcance.
- No es un escaneo de secretos de todo el historial Git ni de configuracion remota.

CodeQL 2.27.4 instalado; base Python extraida y finalizada: 99/99 archivos,
35936 lineas, cero errores de extractor. El verificador local se adapto a la
representacion `C_/` de rutas Windows en el archivo de fuentes. **Pendiente**:
enumerar fuentes/sumideros, completar modelos, verificar suite y ejecutar consultas;
TypeScript tampoco analizado con CodeQL. Una base construida no es un escaneo terminado.

Los artefactos locales estan en `artifacts/quality-20261112/` y no se versionan:
manifiestos Semgrep/SARIF, base CodeQL, conversacion, revision dimensional y benchmark.
Las herramientas de analisis estan aisladas de las dependencias de produccion.
Hypothesis 6.170.15 queda solo en dependencias de desarrollo.

## Rendimiento e infraestructura

Prueba HTTP local: 10 clientes sinteticos, dos trabajos de 4000 filas, dos cuentas
de prueba. Ambos aceptados (202), terminan en 2.953 y 4.501 segundos observados y
concuerdan con el total independiente. Acceso al trabajo ajeno: 404. Pico RSS:
193.56 MiB; p95 de las peticiones muestreadas: 435.06 ms. Cero peticiones de carga a
produccion, cero archivos de clientes, cero subidas a Storage.

Estos numeros describen ese laboratorio, **no diez clientes comerciales
certificados** ni el rendimiento de Render. La lectura operativa del 12 de noviembre
mostro instancia gratuita, una replica, 0.15 CPU y 512 MiB; no se cambio el plan.
Sin series utiles de peticiones/latencia de produccion no se infiere capacidad vendible.

Microbenchmark de formateo CLP: 20000 llamadas, resultados identicos, 1113.85 ms al
crear formateador por llamada frente a 19.13 ms reutilizandolo. No es una aceleracion
equivalente de la plataforma completa ni de la limpieza de archivos.

## Pendientes y limites

1. Completar CodeQL y revisar sus hallazgos antes de declararlo aplicado.
2. Verificar en vivo registro, confirmacion y recuperacion de correo. Gmail para
   alertas operativas no demuestra que Supabase Auth entregue esos mensajes.
3. Mantener comprobaciones de aislamiento en cada nueva ruta con service-role;
   revalidar RLS/configuracion desplegada de forma separada.
4. Capacidad sostenida representativa y restauracion completa fuera del proveedor.
   El respaldo externo sigue pospuesto por indicacion del usuario; retencion solo revision.
5. Publicacion/CI y comprobacion de la version remota son pasos independientes de
   las pruebas locales. No afirmar despliegue por el mero hecho de guardar este informe.

El modelo de amenazas complementario esta en
`docs/ads-veris-analytics-platform-threat-model.md`. No se declara una plataforma
imposible de vulnerar ni una certificacion comercial a partir de estas pruebas.
