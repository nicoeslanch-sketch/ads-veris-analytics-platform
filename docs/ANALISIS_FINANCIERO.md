# Guía de análisis financiero ADS Veris — ratios, relaciones y decisiones

Referencia oficial del producto (Fase 19). Define QUÉ debe medir la plataforma,
CÓMO se relacionan las tablas de un negocio y QUÉ decisión gatilla cada
indicador. La regla editorial de la interfaz sale de aquí:

> **Resumen muestra los números y resultados contables/económicos.
> Explorar datos interpreta esos números para tomar decisiones.**

La secuencia del analista que la plataforma debe reproducir:
**número → ¿es normal? (tendencia + comparación) → ¿por qué? (causa raíz) → ¿qué hago? (decisión)**.
Un ratio aislado no es una respuesta: es una pregunta.

---

## 1. Estados financieros (la materia prima)

| Estado | Pregunta | Naturaleza |
|---|---|---|
| Estado de Resultados (EERR) | ¿Gané o perdí en el período? | Flujo |
| Balance | ¿Qué tengo y qué debo hoy? | Foto |
| Flujo de Efectivo (EFE) | ¿Entró o salió caja de verdad? | Flujo |

Cascada del EERR: Ventas netas (SIN IVA) − COGS = **Margen bruto** − GAV =
**EBITDA** − depreciación = **EBIT** − intereses = resultado antes de impuesto
− impuesto = **utilidad neta**. Cada línea se lee como **% de las ventas**
(análisis vertical).

Reglas que el motor ya aplica y debe seguir aplicando:

- **El IVA no es ingreso**: los indicadores usan montos netos; el IVA se
  valida por fila (tasa inferida de la propia columna) pero jamás se suma como
  venta.
- **La utilidad es opinión, la caja es realidad**: facturar ≠ cobrar. Los
  pagos `Pendiente`/`Reversado` de una hoja de cobranzas no son recaudación.
- **Los estados se conectan**: la utilidad alimenta el patrimonio; la caja del
  EFE es la caja del balance. ROA/ROE/liquidez se habilitan solo cuando el
  usuario conecte datos de balance (contrato actual de
  `indicadores_financieros.disponible=false` — no inventar).

## 2. Familias de ratios y decisión que gatillan

| Ratio | Fórmula | Rango sano* | Gatilla acción |
|---|---|---|---|
| Razón corriente | Act. corriente / Pas. corriente | 1,2–2,0 | < 1 o > 2,5 |
| Prueba ácida | (Act. corr. − Inventario) / Pas. corr. | ≥ 1,0 | brecha grande vs razón corriente ⇒ "tu liquidez es inventario" |
| Días inventario (DIO) | 365 / (COGS / Inv. promedio) | según rubro | tendencia al alza |
| Días de cobro (DSO) | 365 / (Ventas crédito / CxC prom.) | ≤ política de crédito | sobre la política ⇒ financias gratis a tus clientes |
| Días de pago (DPO) | (CxP prom. / COGS) × 365 | negociado | — |
| **Ciclo de caja (CCC)** | DIO + DSO − DPO | lo más bajo posible | al alza ⇒ el crecimiento consume caja |
| Endeudamiento | Pasivos / Activos | 0,4–0,6 | > 0,7 |
| Cobertura de intereses | EBIT / gastos financieros | > 3,0 | < 2,0 |
| Deuda / EBITDA | Deuda neta / EBITDA | < 3,0x | > 4,0x |
| Margen bruto/EBITDA/neto | sobre ventas | según rubro | a la baja sostenida |
| ROE (DuPont) | margen × rotación × apalancamiento | > costo de oportunidad | < depósito a plazo |
| **LTV / CAC** | valor del cliente / costo de captarlo | ≈ 3:1 | < 1 crítico |
| Concentración cliente/producto | % ventas del top 1 | < 20–25% | > 25% ⇒ diversificar |
| Punto de equilibrio | Costos fijos / margen de contribución % | — | ventas cerca del BE |

\* Rangos referenciales; el benchmark válido es la industria del usuario y su
propia tendencia. **La plataforma compara contra las medianas del propio
archivo** (así funciona la clasificación de portafolio) y nunca presenta un
rango abstracto como veredicto.

Red flags del tablero (la base de los "Hallazgos" y Alertas):
caja cae con ventas subiendo (CCC largo) · prueba ácida ≪ razón corriente ·
DSO subiendo · margen bruto estable con neto cayendo · cobertura de intereses
< 2 · un cliente > 25% · LTV/CAC < 1 · inventario creciendo más rápido que
las ventas.

## 3. Portafolio de productos (matriz volumen × margen)

Clasificación implementada en `analisis_rentabilidad` (Explorar):

| Cuadrante | Volumen | Margen | Acción |
|---|---|---|---|
| Estrella | alto | alto | invertir y promocionar |
| Vaca lechera | alto | bajo | optimizar costo de adquisición/logística |
| Oportunidad | bajo | alto | marketing/venta cruzada para subir volumen |
| Problema | bajo | bajo/negativo | rediseñar precio, renegociar costo o descontinuar |

Umbrales = **medianas del archivo** (participación bruta y margen pareado).
Complementos ya implementados: productos con margen negativo, **ventas bajo el
costo** (con la pérdida bruta que explican), filas con margen atípico (IQR) y
margen bruto mes a mes. El margen agregado SIEMPRE es
`SUM(utilidad) / SUM(venta neta)`, nunca el promedio simple de márgenes por
fila.

## 4. Modelo relacional de un negocio (multihoja)

Dimensiones: Productos (SKU), Clientes (ID_Cliente), Proveedores, Sucursales,
Vendedores, Calendario, Costos vigentes (1 fila/SKU), Historial de costos
(SKU + vigencia). Hechos: Ventas (documento/línea), Compras, Inventario
(foto por fecha+sucursal+SKU), Cobranzas (pago), Gastos, Metas (mes+sucursal).

Relaciones seguras (muchos-a-uno, validadas por el detector actual):
Ventas→Productos/Costos_Productos/Clientes/Sucursales/Vendedores por sus IDs;
Inventario→Productos+Sucursales; Compras→Productos/Proveedores/Sucursales;
Cobranzas→Clientes; Gastos→Proveedores/Sucursales; Metas→Sucursales (+mes).

**Uniones que NUNCA deben ejecutarse como join simple** (el detector las
bloquea y esta es la razón):

1. `Ventas → Historial_Costos` solo por SKU: hay N vigencias por producto —
   multiplicaría cada venta. Requiere unión temporal (*as-of join*): el costo
   con `fecha_vigencia <= fecha_venta` más reciente. **Pendiente**.
2. `Ventas → Cobranzas` por documento: uno-a-muchos — primero agregar pagos
   `Aplicado` por documento, luego unir; `total_documento − cobrado` = saldo.
   **Pendiente** (hoy Cobranzas se analiza como hoja operacional).
3. Totales de documento repetidos en cada línea: no sumar desde el detalle.
4. Metas: unir contra ventas YA agregadas por mes+sucursal, no fila a fila.
5. Inventario: es una foto — los snapshots no se suman entre fechas.

Riesgo central que el motor ya controla: una unión jamás puede cambiar filas
ni totales (validación de cardinalidad y conservación de montos en
`join_related_frames`).

## 5. Catálogo de métricas por área (mapa de implementación)

| Área | Implementado hoy | Pendiente priorizado |
|---|---|---|
| Ventas | neta/bruta, unidades, documentos, ticket, evolución, crecimiento MoM, mix por producto/categoría/canal/sucursal/día, devoluciones con signo, tasa de anulación, concentración | crecimiento interanual (YoY) explícito, venta nueva vs recurrente |
| Rentabilidad | costo pareado, utilidad, margen ponderado, portafolio 4 cuadrantes, margen negativo, ventas bajo costo, margen mensual, outliers de margen | efecto precio/costo/mix (variance analysis), punto de equilibrio (requiere clasificar gastos fijos/variables) |
| Clientes | únicos, top, concentración, cobertura de identificación | RFM, retención/churn, LTV/CAC (requiere gasto comercial), días entre compras |
| Inventario | stock, valorizado, bajo mínimo, negativos, por sucursal, diferencias de conteo | rotación/DIO y GMROI (requiere unir COGS con inventario promedio), cobertura en días, lento movimiento |
| Compras/Proveedores | totales, unidades, perfil operacional | variación de precio de compra, lead time, concentración de proveedor, score |
| Cobranzas | perfil operacional, estados de pago | saldo por documento, aging (1-30/31-60/…), DSO, sobrepagos, pagos huérfanos |
| Caja | — | flujo operativo entradas−salidas, CCC (necesita DSO+DIO+DPO) |
| Metas | perfil (subtipo metas) | cumplimiento real vs meta por mes+sucursal, proyección de cierre |
| Calidad de datos | duplicados exactos/posnormalización, conflictos de ID, totales estructurales, IVA/total que no cuadran, costos peligrosos, porcentajes fuera de rango, montos vs cantidad×precio×(1−desc), huérfanos de la relación activa | huérfanos de TODAS las relaciones declaradas, sobrepagos, frescura de maestros |

## 6. Errores típicos de PyME que la plataforma vigila

1. Confundir utilidad con caja (facturado ≠ cobrado).
2. Sumar el IVA como ingreso (el motor usa montos netos y valida la tasa).
3. Sumar filas TOTAL del archivo junto a las transacciones (excluidas Fase 19).
4. Contar ventas anuladas como ingreso (excluidas; devoluciones con signo).
5. Margen agregado como promedio de márgenes por fila (se usa el ponderado).
6. Comparar meses consecutivos en negocios estacionales (preferir interanual).
7. Ratios sobre datos sucios: por eso la limpieza señala TODO sin corregir en
   silencio — "calidad de los datos primero" es un principio del producto.
