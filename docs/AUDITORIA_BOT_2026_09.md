# Bot: conversaciones y alcance de las respuestas

## Resultado

El bot sigue siendo determinista y gratuito, sin consumo de un modelo de IA ni
ADS Coins. Se ampliaron sus capacidades conversacionales sin presentarlo como
inteligencia artificial general. La biblioteca financiera existente sigue siendo
la fuente de las explicaciones; las cifras proceden de los indicadores visibles.

La ronda inicial encontro 22 fallos en 29 turnos sinteticos. Tras corregirlos y
ampliar el ensayo, pasan **84 turnos en 19 conversaciones**. Las conversaciones
incluyen cambios de tema, comparaciones, cortes temporales, correcciones y
preguntas sobre importacion, descarga, limpieza y soporte.

## Cambios

- Consulta valores de meses identificados, rangos inclusivos y comparaciones
  dirigidas. No confunde el total anual con una fecha diaria. Si enero aparece
  en varios anos, pregunta cual y admite una respuesta corta con el ano.
- Reconoce segmentos por su nombre exacto sin corregir los nombres de clientes
  o productos como si fueran palabras financieras. Amplia el vocabulario de
  meses y errores como `enreo`, `febreo` y `marso`; separa frases pegadas.
- Rechaza cruces no publicados, exclusiones nuevas y medidas incompatibles:
  unidades no se contestan en pesos; ingresos no sustituyen margen ni IVA.
- Una pregunta posterior por un mes no pierde silenciosamente el segmento
  anterior. Las preguntas multiples se responden por separado, hasta tres.
- Conserva UF/CLP/USD y no inventa tipos de cambio. Mes ausente no significa
  cero; variacion con base cero no se presenta como porcentaje definido.
- Distingue promedios de sumas y advierte cobertura parcial. No atribuye
  causalidad ni certifica rentabilidad sin costos comparables.
- Cambiar archivo, hoja, reglas o filtros inicia un hilo nuevo y cancela la
  respuesta pendiente del alcance anterior. Hay reinicio manual y sugerencias
  sucesivas; texto largo y palabras sin espacios se ajustan en movil.
- Las preguntas numericas no consultan la base de articulos. El catalogo
  compartido se cachea 120 segundos, sin cachear datos privados entre usuarios.
  El calculo determinista corre fuera del event loop. Se acota la estructura
  de contexto y se recupera la memoria de los limitadores inactivos.

## Verificacion

`python scripts/exercise_assistant.py --output tmp/bot-conversation-final.json`
genera las conversaciones completas, expectativas y tiempos con datos ficticios.
Los archivos de salida quedan ignorados por Git. La corrida final registro una
mediana de 1,224 ms y p95 de 7,501 ms por respuesta interna local: **no son
latencias de red ni una medicion de usuarios concurrentes en Render**.

`api/tests/test_assistant_conversation_audit.py` agrega 82 casos automatizados,
incluyendo las 19 conversaciones, matriz de erratas/mes/moneda, contextos
invalidos, cache y rechazo de subtotales desconocidos. Las 130 pruebas anteriores
de soporte, lenguaje financiero y regresiones tambien pasan.

`frontend/e2e/bot_context.spec.ts` verifica el contrato real de indicadores,
historial, cambio de hoja/periodo, respuestas tardias y texto largo. El endpoint
de respuesta se simula en esas tres pruebas para controlar las carreras; las
84 conversaciones anteriores ejecutan el motor real, no respuestas simuladas.

## Limites

No entiende todas las preguntas posibles ni ejecuta filtros nuevos sobre filas
desde el chat. Solo calcula a partir de agregados que el motor publica; cuando
falta el cruce o la fuente pide aclaracion o dirige a Explorar. Esta frontera
evita respuestas convincentes pero incorrectas. Una prueba aprobada no garantiza
que todas las formas de escribir una pregunta esten cubiertas.
