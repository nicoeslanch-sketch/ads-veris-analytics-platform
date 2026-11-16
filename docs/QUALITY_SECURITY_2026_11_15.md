# Reportes y revision CodeQL - 2026-11-15

## Alcance

Base `018435f598b53b798ab78d716bae06d4012be712`. Revision local autorizada de
`api/app` y `frontend/src`; sin ataques a produccion, contrataciones, activacion
de IA/pagos ni subida del codigo a un servicio de escaneo.

## Correcciones verificadas

- CSV: moneda del resultado, no CLP fijo; conserva la precision numerica recibida
  (por ejemplo UF 0.004), sin redondear todos los importes a dos decimales.
- Impresion: moneda explicita del reporte independiente de la moneda global de
  la sesion. Conserva fracciones UF y centavos de monedas extranjeras. No publica
  NaN o Infinity como importes. Los limites de precision UF tambien se escapan.
- Las etiquetas de porcentajes de grupos explican la base neto/ventas brutas.
- Impresion compatible con CSP sin scripts inline. Apertura del documento antes
  de registrar el evento de carga; ventana sin acceso de regreso via opener.
- Grilla de indicadores y tablas adaptables, con prueba de desbordamientos a
  320 y 1280 px. Se mantiene el escape de nombres de archivo, empresa y grupos.
- Reportes de demo disponibles con empresa ficticia; el componente de metricas
  reales no se monta en demo y no se consulta el perfil para identificarla.
  La comprobacion de capacidad del plan se conserva.

Verificacion local: 292 tests de frontend, build TypeScript/Vite y prueba
Playwright de impresion con CSP pasan. Capturas de escritorio y movil revisadas.
La prueba de navegador simula el dialogo de impresion, no genera un PDF binario
ni sustituye la comprobacion del dialogo nativo en todos los navegadores.

## CodeQL: herramientas y cobertura

CodeQL 2.27.4; modo important-only con consultas experimentales de seguridad,
precision media/alta y filtrado posterior por severidad. Entradas remotas por
defecto mas entradas de archivos. Suites explicitas generadas y verificadas:

- Python: 77 consultas (66 oficiales, 11 comunitarias).
- JavaScript/TypeScript: 136 consultas (126 oficiales, 10 comunitarias).
- Paquetes oficiales: python-queries 1.9.0 y javascript-queries 2.5.0.
- Paquetes comunitarios githubsecuritylab/codeql-python-queries y
  codeql-javascript-queries 0.9.0; modelos codeql-python-extensions 0.9.0.
- Procedencia: GitHubSecurityLab/CodeQL-Community-Packs, licencia MIT,
  revision empaquetada 8ae37732eed8a254baf109b9b6fd21e1623c6fcc.

Python: 99/99 archivos, 35949 lineas, cero errores de extraccion; control de
calidad aprobado. Diagnosticos: 350 fuentes FastAPI, 129 sumideros (82 HTTP,
36 archivos, 11 decodificacion). Algunos parametros inyectados por Depends son
sobreaproximados como entradas; el buffering ASGI personalizado requiere revision
manual y no queda cubierto por completo por estos modelos.

Frontend: 121 archivos de proyecto en la extraccion inicial, cero errores;
231 contando externs del extractor. Diagnosticos: 29 fuentes remotas y 33
sumideros (7 HTML, 26 escrituras URL). Las pruebas no se incluyen en el alcance.
La primera evaluacion de seguridad agoto el heap Java con presupuesto de 2048 MiB.
La repeticion con extraccion actualizada, un hilo y 4096 MiB completo las 136
consultas: 26272 lineas, calidad aprobada y cero errores de extraccion. Se
encontraron 10 resultados, todos retenidos por el filtro (2 error, 8 warning).
No se interpreta una ejecucion fallida como cero hallazgos.

## Revision de los hallazgos frontend

- Dos `js/xss-more-sources` (precision alta, severidad 6.1): navegacion al enlace
  devuelto por exportaciones de consolidacion y href de Google Sheets guardado.
  Las fuentes del backend son URL firmada de Storage y URL canonica de Google,
  respectivamente; no se demostro una via normal de usuario para guardar un
  javascript: en ellas. Se refuerza de todas formas la frontera del navegador:
  solo HTTPS absoluto, sin credenciales ni caracteres de control/backslash;
  origen exacto docs.google.com para los enlaces de Sheets. No se debilita CSP.
- Ocho `js/remote-property-injection-more-sources` (precision media, severidad
  7.5): una ubicacion en changeRole y siete flujos en los campos de configuracion.
  No se confirma prototype pollution: el codigo usa propiedades calculadas de
  literales, spread y Object.fromEntries, no setters sobre Object.prototype,
  asignacion dinamica a objetos compartidos ni merges recursivos. Los ids son
  claves de decisiones del componente, no decisiones de autorizacion. Se
  conservan las alertas en SARIF sin agregar supresiones ni sanitizadores falsos.

Se repite la extraccion y el analisis despues del refuerzo de navegacion. Las
pruebas de URL incluyen javascript/data, credenciales, controles, rutas relativas,
host parecido a Google y conservacion de query de descarga firmada. La prueba
de navegador recibe enlaces sinteticos hostiles sin visitar destinos externos.

## Revision de los hallazgos Python

Tres resultados brutos, todos retenidos por el filtro important-only:

| Regla | Lugar | Evaluacion |
|---|---|---|
| py/prompt-injection | routes/ai.py:337 | Riesgo real condicionado a activar proveedor: etiquetas/valores del cliente llegan al prompt de resumen |
| py/prompt-injection | routes/ai.py:415 | Mismo riesgo en recomendacion, incluyendo analisis y hallazgos libres |
| py/unicode-bypass-validation | engine/mapping.py:34 | No se confirma bypass de autorizacion; normalizacion intencional para interpretar encabezados/instrucciones de limpieza |

Las alertas de prompt tienen precision alta y puntuacion 5.0. No se suprimen:
la IA debe tratar los datos como contenido no confiable, validar contratos de
entrada y probar respuestas adversarias antes de activar el proveedor. Separar
instrucciones y datos en el prompt ayuda, pero no prueba inmunidad. Estas rutas
no entregan herramientas al modelo ni claves del servidor en el prompt. El chat
tambien necesita esa evaluacion aunque la consulta no lo haya senalado. No se
activa ni se cambia el proveedor en este cambio; el bot determinista es separado.

El flujo Unicode senalado pasa por instrucciones limitadas a 2000 caracteres,
interpretacion determinista y seleccion entre columnas/reglas existentes. Las
comprobaciones de usuario/capacidad/propiedad del archivo estan fuera de esa
normalizacion. No se elimina NFKD: romper tildes y equivalencias de encabezados
para silenciar una alerta seria una regresion. Reevaluar si se reutiliza para
identidad, rutas, permisos o consultas SQL.

## Dependencia de desarrollo

GitHub Dependabot aviso GHSA-8g5g-mxqh-grgj en Vite 6.4.4. Se actualiza a 6.4.6
y se agrega una prueba HTTP con archivo sintetico .crt y variantes raw/import
para comprobar que no se evade server.fs.deny. El aviso del mantenedor afecta
al servidor de desarrollo expuesto a la red, no al bundle estatico de produccion.
No se usan archivos .env reales ni certificados privados para comprobarlo.

## Limites de la revision

Estos escaneos no certifican aislamiento de toda la base, configuracion remota,
capacidad comercial, recuperacion completa ni ausencia de vulnerabilidades.
Los artefactos detallados permanecen locales en `artifacts/quality-20261115/`.
La publicacion y los checks de CI se registran por separado en la PR.
