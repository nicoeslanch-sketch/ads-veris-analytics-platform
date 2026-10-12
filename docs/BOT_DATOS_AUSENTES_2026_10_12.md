# Bot: ausencia de ventas no equivale a cero

## Caso corregido

En una vista de catalogo, despues de consultar ingresos, la pregunta
"entonces tengo cero ventas?" caia en una definicion de ventas netas.
El bot ahora explica que faltan transacciones y que eso no demuestra ventas
iguales a cero. Dirige a una hoja de ventas o Vision del negocio.

## Limites conservados

- Los precios de lista y costos unitarios no se suman como ingresos o gastos.
- Los ceros reales publicados en indicadores siguen siendo ceros.
- Las preguntas breves sucesivas conservan el tema, con historial acotado.
- Un cambio explicito a costos, stock, clientes, duplicados o creditos no
  hereda automaticamente la pregunta anterior sobre ventas.
- Se reconocen palabras pegadas y la errata "bentas" mediante vocabulario
  controlado, sin activar un proveedor de IA ni consumir ADS Coins.

## Verificacion reproducible

- `api/tests/test_assistant_conversation_audit.py`: matriz CLP/UF, ceros
  reales, contexto ausente, cambio de tema y catalogo sin perfil publicado.
- `api/tests/assistant_scenarios.py`: conversacion adicional de diez turnos.
- `python scripts/exercise_assistant.py --output artifacts/bot-20261012/conversations.json`.
- Suite backend completa y controles obligatorios del PR antes de fusionar.

Las conversaciones de esta bateria son sinteticas y locales. No certifican
todas las preguntas posibles ni la capacidad comercial del servidor. No se
modifican datos de clientes, infraestructura, cuotas ni pagos.
