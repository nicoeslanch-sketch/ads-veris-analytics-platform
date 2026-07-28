# Relevo técnico — modelo de servicios y libro `Prueba_Servicios_SUCIO_v2`

Fecha de corte: 28 de julio de 2026
Repositorio: `nicoeslanch-sketch/ads-veris-analytics-platform`
Rama de entrega: `main`
Commit funcional desplegado: `f47e475fc9407b8f9439f093783b28c43b817a54`
Motor declarado por `/version`: `0.25.0`

## Propósito de este documento

Este archivo permite retomar el trabajo desde otra cuenta o equipo sin reconstruir el contexto de la conversación. Separa explícitamente:

1. lo que ya está implementado y probado;
2. lo que está desplegado;
3. las comprobaciones manuales todavía pendientes;
4. las limitaciones técnicas conocidas;
5. el orden recomendado para completar el trabajo.

No se debe rehacer lo marcado como terminado salvo que una prueba reproducible demuestre una regresión.

## Solicitud funcional que originó el cambio

El libro de servicios no usa nombres convencionales de ventas. Su fuente comercial principal es `Detalle_OT`:

- las líneas `Material` usan `MONTO` como venta neta;
- las líneas `Subcontrato` usan `MONTO` como costo directo, no como venta;
- `CANTIDAD`, `PRECIO UNITARIO` y `DESCUENTO` permiten verificar la fórmula comercial;
- las horas facturables generan ingreso al relacionarlas con una tarifa de venta vigente;
- todas las horas generan costo al relacionarlas con una tarifa de costo vigente;
- la visión completa requiere conectar órdenes, detalle, horas, tarifas, técnicos, clientes, contratos, cuotas, UF y gastos;
- ninguna hoja comparte el esquema de otra, por lo que **Unir periodos de venta no aplica**;
- compartir `ID_OT` no basta para apilar tablas.

Además, la descarga fallaba con:

```text
No se exportó un libro parcial. Corrige o reintenta estas hojas:
Detalle_OT: name 'pd' is not defined
```

## Estado terminado

### 1. Error de exportación corregido

La causa raíz estaba en `api/app/routes/pipeline.py`: `_export_annotations` utilizaba `pd.Series` sin que `pandas` estuviera importado en el ámbito del módulo.

La corrección:

- elimina el `NameError`;
- conserva la prohibición de entregar un libro parcial;
- mantiene las anotaciones de exportación;
- fue validada exportando el libro real mediante el flujo interno.

La exportación local completa tardó aproximadamente **14,8 segundos** en el equipo de prueba.

### 2. Modelo específico de servicios incorporado

El módulo central es:

```text
api/app/engine/service_model.py
```

Este módulo:

- detecta el libro por evidencia estructural, no únicamente por el nombre del archivo;
- modela las 11 hojas del caso;
- conserva `Detalle_OT` como fuente transaccional;
- separa `Material` de `Subcontrato`;
- rellena de forma controlada los identificadores de OT en las líneas de continuación;
- excluye subtotales estructurales;
- empareja tarifas por técnico y vigencia;
- convierte cuotas expresadas en UF usando el valor del periodo;
- transforma los gastos mensuales anchos a un formato analítico;
- calcula indicadores solo cuando existe evidencia suficiente;
- evita presentar como ventas las tarifas, los contratos, la UF o las banderas booleanas;
- permite análisis exploratorio de `Detalle_OT` sin exigir relaciones;
- reserva la Visión del negocio completa para la red de fuentes necesaria.

### 3. Métricas del libro real reconciliadas

Los controles obtenidos con el archivo real son:

| Indicador | Valor |
|---|---:|
| Ventas / ingresos | $1.588.201.934 |
| Costo directo | $975.807.518 |
| Utilidad bruta | $612.394.416 |
| Margen bruto | 38,56% |
| Gastos de estructura | $474.900.000 |
| Resultado operacional | $137.494.416 |
| Margen operacional | 8,66% |
| EBITDA | $170.818.416 |
| Margen EBITDA | 10,76% |
| Utilización técnica | 81,98% |
| Costo no facturable | $43.852.089 |
| Backlog | $111.986.987 |
| OT con pérdida bruta | 185 |
| OT con pérdida operacional | 946 |
| Ingreso recurrente | $458.859.110 |

No reemplazar estas cifras por valores aproximados sin volver a verificar el mismo archivo fuente.

### 4. Limpieza estructural validada

La descarga de validación contiene estas dimensiones:

| Hoja | Filas | Columnas |
|---|---:|---:|
| Ordenes_Trabajo | 1.295 | 15 |
| Detalle_OT | 4.021 | 10 |
| Horas_Tecnicos | 7.079 | 7 |
| Tarifas_Tecnicos | 36 | 6 |
| Tecnicos | 18 | 6 |
| Items | 90 | 7 |
| Clientes | 140 | 8 |
| Contratos | 58 | 8 |
| Cuotas | 676 | 7 |
| Valor_UF | 12 | 3 |
| Gastos | 180 | 5 |

La auditoría generada incluye:

- 80 registros de `fila_resumen_estructural`;
- 1 registro de continuación estructural;
- 13 duplicados exactos eliminados tras confirmación;
- trazabilidad `fila_estructural_excluida`;
- confirmación determinista de las reglas estructurales.

La guía adjunta hablaba de 78 subtotales y 2.716 propagaciones, pero la versión exacta del libro entregado produjo 80 subtotales y 2.726 propagaciones. El resultado final de 4.021 líneas y los controles financieros sí coinciden. Antes de cambiar el motor para forzar 78/2.716, comparar las versiones binarias de los libros: la diferencia parece estar en la fuente, no en el cálculo final.

### 5. Experiencia de usuario incorporada

Se agregó `frontend/src/components/ServiceBusinessPanel.tsx` con:

- 14 KPI;
- 9 visualizaciones;
- cascada económica;
- dispersión de órdenes por ingreso y utilidad;
- evidencia de fuentes utilizadas;
- estados de dato faltante;
- bloqueo de indicadores que no tienen relaciones suficientes.

También se incorporó:

- explicación de que `Detalle_OT` puede contener ventas aunque no se llame `Ventas`;
- bloqueo de `Unir periodos` para este libro;
- orientación hacia `Relación manual`;
- plan recomendado de relaciones y qué indicador desbloquea cada paso;
- tipos TypeScript para el nuevo perfil;
- integración del panel con la Visión del negocio.

### 6. Archivos del cambio funcional

```text
api/app/engine/audit.py
api/app/engine/business.py
api/app/engine/metrics.py
api/app/engine/quality.py
api/app/engine/relationships.py
api/app/engine/service_model.py
api/app/routes/pipeline.py
api/tests/test_dashboard_audit_2026.py
api/tests/test_service_model.py
frontend/src/components/ActiveSheetSelector.tsx
frontend/src/components/AdaptiveProfileSummary.tsx
frontend/src/components/BusinessAnalysisPanel.tsx
frontend/src/components/ServiceBusinessPanel.tsx
frontend/src/components/relationships/RelationshipWorkspace.tsx
frontend/src/lib/types.ts
```

## Pruebas ya ejecutadas

Resultados del commit funcional:

| Suite | Resultado |
|---|---|
| Backend pytest | 554 aprobadas; 9 advertencias deprecadas |
| Frontend Vitest | 115 aprobadas |
| TypeScript | correcto |
| Build frontend | correcto; 2.310 módulos |
| Playwright local | 12 aprobadas |
| `git diff --check` | correcto |
| Búsqueda de secretos | sin coincidencias |
| Exportación real | correcta; aproximadamente 14,8 s |

Comandos de reproducción:

```powershell
git checkout main
git pull --ff-only origin main
git rev-parse HEAD

Set-Location api
python -m pytest -q

Set-Location ..\frontend
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e
```

## Estado de despliegue verificado

En el momento del corte:

- GitHub Actions estaba en verde para el commit funcional;
- Vercel informó despliegue exitoso;
- el frontend respondió HTTP 200;
- Render `/health` respondió:

```json
{"status":"ok","service":"ads-veris-data-engine"}
```

- Render `/version` informó el SHA funcional:

```text
f47e475fc9407b8f9439f093783b28c43b817a54
```

- `database_migration: "0021"` en `/version` es una constante informativa del código. En este trabajo **no se ejecutó ninguna migración**.

## Trabajo pendiente — prioridad P0

### P0.1 Validación visual completa en producción tras recarga forzada

La sesión del navegador mantenía JavaScript anterior montado cuando terminó el despliegue. El backend ya exponía el nuevo SHA, pero la página visible no se había recargado completamente.

Procedimiento:

1. abrir la plataforma en una pestaña nueva o hacer recarga forzada;
2. volver a cargar `Prueba_Servicios_SUCIO_v2 (1).xlsx`;
3. seleccionar las 11 hojas de datos;
4. ejecutar estandarización y limpieza;
5. confirmar la eliminación de los 13 duplicados exactos;
6. descargar el XLSX;
7. comprobar que no aparezca `name 'pd' is not defined`;
8. abrir Visión del negocio;
9. comprobar los 14 KPI y las 9 visualizaciones;
10. contrastar los KPI con la tabla de métricas de este documento;
11. revisar responsive en escritorio y móvil;
12. guardar capturas de cualquier diferencia con el nombre de la vista y el filtro activo.

Esta validación es manual y todavía no debe declararse completada.

### P0.2 Restauración de archivos antiguos desde Historial

Los snapshots limpios creados antes del nuevo modelo pueden contener:

- roles anteriores;
- relaciones anteriores;
- resultados precalculados con una versión previa;
- un perfil sin `service_model`.

El nuevo procesamiento se ejecuta en `_analyze_uncached`, pero un snapshot histórico puede mostrar primero información vieja.

Solución recomendada:

1. agregar una versión explícita al perfil/modelo de servicios;
2. incluirla en la clave de caché y en el estado restaurado;
3. invalidar solo los derivados analíticos antiguos, conservando el archivo limpio y su auditoría;
4. recalcular en segundo plano una sola vez;
5. evitar crear otra actividad de “limpieza completada” durante ese recálculo;
6. agregar una prueba de restauración premodelo → modelo actual;
7. probar navegación Historial → Resumen → Explorar → Historial sin bucles.

No borrar snapshots históricos ni forzar una limpieza completa si basta con recalcular los indicadores.

### P0.3 Completar el catálogo de relaciones manuales

El panel muestra el plan conceptual de 12 pasos, pero no todas las relaciones son todavía conexiones ejecutables en el catálogo.

Con el libro recién procesado se detectaron de forma segura:

1. `Ordenes_Trabajo → Clientes`;
2. `Cuotas → Contratos`;
3. `Detalle_OT → Ordenes_Trabajo`;
4. `Horas_Tecnicos → Ordenes_Trabajo`;
5. `Horas_Tecnicos → Tecnicos`;
6. `Tarifas_Tecnicos → Tecnicos`;
7. `Detalle_OT → Items`.

Relaciones que requieren trabajo adicional:

- `Horas_Tecnicos → Tarifas_Tecnicos`: join temporal por técnico y fecha de vigencia, no join simple;
- `Cuotas → Valor_UF`: relación por periodo normalizado; volver a probar después de la canonización de periodo;
- `Ordenes_Trabajo → Contratos`: relación opcional o de cobertura parcial;
- `Ordenes_Trabajo → Tecnicos`: resolver semánticamente Supervisor frente a Código Técnico sin inventar equivalencias;
- `Contratos → Clientes`: validar cobertura y cardinalidad;
- `Gastos → Periodo`: es una alineación temporal analítica, no una relación de clave tradicional.

Reglas:

- no mostrar conexiones con cero solapamiento;
- no ofrecer joins muchos-a-muchos que multipliquen filas;
- no forzar estas relaciones solo para alcanzar el número 12;
- un join temporal debe validar vigencia, solapamientos y huecos;
- explicar con lenguaje simple qué desbloquea cada relación.

El dashboard específico ya calcula la visión completa con las 11 fuentes mediante el modelo controlado. Eso no significa que todas las relaciones manuales estén terminadas.

## Trabajo pendiente — prioridad P1

### P1.1 Invalidación de caché por versión

El motor aún declara `0.25.0`. Conviene:

1. decidir una versión nueva para el modelo de servicios;
2. agregar `service_model_version` a las claves de caché;
3. incorporarla al manifiesto exportado;
4. invalidar derivados cuando cambien reglas, mapeos o versión;
5. conservar la compatibilidad del archivo limpio.

No aumentar la versión sin agregar primero las pruebas de restauración.

### P1.2 Diferenciar Resumen y Explorar para servicios

El panel personalizado de Visión del negocio usa actualmente la misma composición base en Resumen y Explorar. Las vistas hoja por hoja sí son distintas, pero el panel empresarial todavía puede diferenciarse más.

Objetivo:

- Resumen: estado de resultados, KPI, evolución, alertas ejecutivas y conclusiones;
- Explorar: dispersión de OT, drivers, segmentación, sensibilidad, cobertura, anomalías y navegación a registros.

No duplicar los mismos 14 KPI en ambas páginas.

### P1.3 Cascada financiera estrictamente acumulativa

La visual actual funciona como puente de barras positivas y negativas. Si se exige una cascada contable clásica:

1. calcular base acumulada;
2. separar aumento, disminución y total;
3. usar barras apiladas transparentes;
4. probar que cada subtotal cierre;
5. añadir etiquetas de fuente y moneda.

### P1.4 Definición de margen de seguridad

El código entrega la definición financiera convencional:

```text
(ventas - punto de equilibrio) / ventas = 22,45%
```

La guía externa llama “margen de seguridad” a:

```text
(ventas / punto de equilibrio) - 1 = 29,0%
```

No intercambiar ambas fórmulas silenciosamente. Recomendación:

- conservar 22,45% como “Margen de seguridad sobre ventas”;
- exponer 29,0% como “Ventas sobre punto de equilibrio” o “Holgura respecto al equilibrio”;
- mostrar fórmula en el tooltip;
- agregar pruebas para ambos valores.

### P1.5 QA de diseño y responsive

Revisar:

- altura del panel con 14 KPI;
- legibilidad de cifras CLP extensas;
- tooltip y leyendas de la dispersión;
- cuadrante negativo de OT;
- orden de tabulación;
- contraste;
- ancho móvil;
- ausencia de espacios en blanco excesivos;
- gráficos sin superposición.

## Trabajo pendiente — prioridad P2

### P2.1 Medición de rendimiento en Render frío

Medir por separado:

- carga;
- estandarización;
- limpieza;
- modelo de servicios;
- exportación fría;
- exportación caliente;
- restauración desde Historial.

Registrar tamaño, filas, SHA del archivo, versión del motor y estado de caché. No aumentar el timeout como sustituto de una corrección.

### P2.2 Exportación persistente o asíncrona

Si la exportación fría vuelve a exceder un tiempo razonable:

- reutilizar el resultado ya materializado;
- persistirlo por dataset + revisión + reglas + mapeo + versión;
- impedir trabajos duplicados;
- usar un único job con estado si todavía no cabe en una petición;
- conservar una ruta síncrona rápida cuando el archivo ya está preparado.

No se implementó exportación asíncrona en este cambio.

### P2.3 Cobertura E2E específica del libro real

Crear una prueba controlada o fixture anonimizado que compruebe:

- `Detalle_OT` se reconoce como fuente comercial;
- `Subcontrato` no aumenta las ventas;
- las tarifas vigentes se aplican correctamente;
- Unir periodos queda bloqueado;
- la exportación termina;
- las cifras principales coinciden;
- Historial no reprocesa indefinidamente.

El archivo real no debe subirse al repositorio si contiene datos sensibles.

## Criterio de finalización

El trabajo puede considerarse cerrado cuando:

- la exportación productiva termina sin `pd` indefinido;
- la Visión del negocio muestra y reconcilia las cifras de control;
- Unir periodos explica que no aplica;
- Relación manual solo muestra conexiones seguras;
- los joins temporales funcionan sin multiplicar filas;
- un snapshot antiguo restaura rápido y recalcula derivados una sola vez;
- Resumen y Explorar tienen objetivos distintos;
- las pruebas unitarias, integración, build, TypeScript y E2E están verdes;
- Vercel y Render exponen el mismo SHA;
- no se aplicaron migraciones innecesarias.

## Secuencia recomendada para la próxima cuenta

1. sincronizar `main` y leer este documento completo;
2. comprobar el SHA desplegado;
3. realizar P0.1 en producción;
4. corregir primero cualquier discrepancia numérica reproducible;
5. implementar P0.2 con pruebas de snapshots antiguos;
6. completar P0.3 sin aceptar relaciones inseguras;
7. ejecutar toda la suite;
8. medir Render frío y caliente;
9. hacer commit y push directo solo si esa sigue siendo la instrucción vigente;
10. documentar cifras, SHA y pruebas reales.

## Restricciones

- No hay migraciones necesarias para el commit funcional.
- No se ejecutaron migraciones en esta entrega.
- No incluir tokens, archivos `.env`, datos reales ni rutas locales en commits.
- No inventar relaciones ni indicadores.
- No cambiar cálculos financieros para ocultar errores.
- No tratar costos faltantes como cero.
- No sumar tablas temporales o snapshots como si fueran movimientos.
- No declarar una prueba manual aprobada si solo se ejecutó una prueba automatizada.
