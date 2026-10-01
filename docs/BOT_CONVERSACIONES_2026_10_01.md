# Conversacion determinista y alcance de las cifras

Se conserva la separacion entre el bot gratuito y la IA avanzada con creditos.
Esta entrega no activa proveedores, cambia cuotas ni consume ADS Coins.

## Fallos reproducidos y corregidos

- Despues de consultar enero, `y cuantos clientes tuve` usaba el conteo de todo
  el archivo. Los seguimientos conservan ahora periodo y segmento; si ese cruce
  no esta publicado, explican la fuente que falta.
- `cuanto gaste en enero` seguido de `y en febrero` podia responder ingresos.
  La medida tambien se conserva durante los seguimientos.
- `ahora el total general` se desviaba a una definicion de cobranza. Ahora
  retoma la medida consultada y restablece el alcance general visible.
- `que porcentaje aporta febrero` devolvia solo el importe. Ahora muestra el
  porcentaje y su numerador/denominador, identificando los meses de la base.
  No convierte promedios o importes con signos mezclados en participaciones.
- `cerrar mi empresa` se confundia con cerrar sesion; ventas futuras y
  escenarios hipoteticos se confundian con cifras historicas. Se explicitan
  los supuestos y las fuentes necesarias, sin simular acciones ni predicciones.
- El bot reconoce `producto mas vendido` y explica por que el ranking de
  ventas no determina el producto mas rentable.
- Se preservan conjugaciones validas de vender/ganar y los nombres de entidades
  al corregir ortografia. Se corrige el genero de `La sucursal consultada`.

## Verificacion

El ejercicio reproducible contiene 115 turnos, con 0 fallos esperados:
`python scripts/exercise_assistant.py --output artifacts/bot-conversation.json`.
El archivo de salida contiene solo ejemplos sinteticos y se conserva fuera de Git.

Las pruebas focalizadas de conversaciones, finanzas, acceso y relaciones pasan
268 casos. Incluyen nombres parecidos a palabras financieras, meses con erratas,
CLP/UF/USD, bases cero/negativas, cambios de tema y ausencia de datos.

Estos resultados prueban los casos cubiertos. No convierten el bot en un modelo
generativo ni certifican que entienda cualquier pregunta posible.
