# Conversaciones sobre cartera de clientes

El bot gratuito sigue siendo determinista. Esta mejora no conecta proveedores
de IA, no habilita pagos y no consume ADS Coins.

## Correcciones

- Preguntar cuantas cuentas por cobrar hay devuelve el conteo publicado de
  cuentas/cuotas con saldo positivo, no un monto ni clientes o facturas unicas.
  Si el conteo no existe o no es valido, no se sustituye por cero.
- El saldo vencido solo usa `cartera_cxc.saldo_vencido` y su estado de cobertura.
  Se informa si el vencimiento es parcial o no hay fecha de corte.
- La proporcion de saldo vencido muestra numerador y denominador. Requiere
  vencimientos completos, importes compatibles y saldo validado positivo.
  No representa el porcentaje de clientes ni de numero de cuentas.
- Dias de cobro, cantidad de clientes deudores, facturas unicas y ranking de
  deudores siguen requiriendo su propio indicador: no se deducen de ventas.
- Un seguimiento sobre cartera conserva periodos y nombres consultados,
  incluidos los que no tenian respuesta. No se reemplaza su resultado por el
  saldo general. Un cambio explicito al total general libera ese alcance.
- `Y las vencidas` pide aclarar si se busca un monto o un numero. Un tema nuevo,
  como ventas, no se transforma en una pregunta de cartera por el historial.
- Se protegen palabras validas como `cantidad`, `rotacion`, `vencidas`, `mora`
  y `proporcion`: el corrector no debe convertirlas en otra medida financiera.

## Evidencia y limites

El ejercicio reproducible `scripts/exercise_assistant.py` incluye 148 turnos
sinteticos con comprobaciones de cifras, fuentes, advertencias y continuidad.
Tambien hay regresiones para conteos invalidos, cero conocido, UF, cartera
bloqueada, vencimiento parcial y porcentajes con denominadores invalidos.

Las pruebas sinteticas no certifican que el bot pueda responder cualquier
pregunta ni que todos los modelos financieros esten disponibles. La respuesta
depende de los indicadores publicados para el archivo y alcance visibles.
