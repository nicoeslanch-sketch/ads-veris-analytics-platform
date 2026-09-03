"""Catalogo determinista del asistente ADS Veris.

No usa modelos, embeddings ni servicios externos. El catalogo se replica en
``support_bot_articles`` de forma best-effort para que soporte pueda editarlo
sin cambiar el motor; esta copia versionada garantiza una respuesta aun si la
base esta temporalmente indisponible.
"""

from __future__ import annotations

import re
from typing import Any

from .language_normalization import normalize_basic, normalize_query
from .metric_assistant import answer_metrics_question


def article(
    key: str,
    category: str,
    title: str,
    triggers: list[str],
    response: str,
    follow_up: str = "¿Quieres que te indique la ruta exacta dentro de la plataforma?",
    priority: int = 50,
) -> dict[str, Any]:
    return {
        "key": key,
        "category": category,
        "title": title,
        "triggers": triggers,
        "response": response,
        "follow_up": follow_up,
        "priority": priority,
        "active": True,
    }


ARTICLES: list[dict[str, Any]] = [
    article("start", "primeros_pasos", "Comenzar", ["como empezar", "como empiezo", "primeros pasos", "que hago primero", "comenzar"], "Empieza en Importar datos. Después revisa Estandarización, corrige los roles de columnas si fuera necesario, ejecuta Limpieza y recién entonces usa Resumen o Explorar datos. Ese orden evita calcular sobre campos mal interpretados.", priority=90),
    article("formats", "importacion", "Formatos admitidos", ["formato", "xlsx", "csv", "xls", "archivo compatible"], "Puedes cargar .xlsx y .csv. Si tienes un .xls antiguo, ábrelo en Excel y guárdalo como .xlsx. La plataforma no modifica el archivo original."),
    article("large_file", "importacion", "Archivos grandes", ["archivo grande", "pesa mucho", "limite", "15 mb", "demora al subir"], "El flujo clásico admite hasta 15 MB por fuente. Para reducir el tiempo elimina hojas decorativas, imágenes, fórmulas volátiles y columnas completamente vacías; conserva las tablas y sus identificadores."),
    article("standardization", "estandarizacion", "Qué hace Estandarización", ["estandarizacion", "estandarizar", "roles de columna", "mapeo"], "Estandarización detecta tipos y propone roles como fecha, monto, producto o cliente. No cambia cifras: prepara un mapeo verificable para que los cálculos posteriores usen la columna correcta."),
    article("mapping_wrong", "estandarizacion", "Corregir un mapeo", ["mapeo incorrecto", "columna incorrecta", "detecta mal", "rol equivocado"], "En Estandarización revisa la columna asignada a cada rol y cámbiala antes de continuar. Un monto de costo asignado como venta puede alterar todos los indicadores; la corrección queda ligada al dataset."),
    article("cleaning", "limpieza", "Qué hace Limpieza", ["que limpia", "limpieza", "datos sucios", "reglas automaticas"], "Limpieza corrige formatos, nulos, duplicados y tipos según reglas visibles. Antes de aplicar puedes revisar problemas y activar o desactivar reglas. El resultado conserva trazabilidad del antes y después."),
    article("cleaning_slow", "limpieza", "Limpieza lenta", ["limpieza lenta", "demora limpiar", "tarda demasiado", "timeout limpieza"], "La primera limpieza de un libro grande puede tardar porque se inspeccionan todas sus hojas. No cierres la pestaña. Las operaciones repetidas reutilizan resultados cuando el archivo, las reglas y la hoja no cambiaron; si aparece un timeout, reintenta una vez y abre Ver detalle."),
    article("download_slow", "limpieza", "Descarga limpia lenta", ["descarga lenta", "demora descargar", "tres minutos", "timeout descarga"], "Exportar un Excel limpio requiere reconstruir todas las hojas y estilos compatibles, por eso suele tardar más que descargar CSV. Si solo necesitas datos, elige CSV; para libros multihoja usa Excel y mantén la pestaña abierta hasta terminar."),
    article("download_clean", "limpieza", "Descargar datos limpios", ["descargar excel limpio", "descargar archivo limpio", "descargar base limpia", "como descargo", "exportar datos limpios"], "Después de aplicar la limpieza, abre Limpieza y usa Descargar datos limpios. Elige Excel para conservar las hojas y la auditoría, o CSV para una salida más liviana. La descarga usa la misma configuración de reglas, mapeo y duplicados que quedó guardada para el dataset."),
    article("duplicates", "calidad", "Duplicados", ["duplicados", "filas repetidas", "id duplicado", "eliminar duplicados"], "No se decide un duplicado solo por posición. La plataforma compara claves y contenido, muestra cuántos detectó y aplica la regla elegida. Si un ID se repite con información distinta, debe revisarse como conflicto y no borrarse arbitrariamente."),
    article("missing", "calidad", "Valores faltantes", ["nulos", "vacios", "faltan datos", "sin valor"], "Los valores faltantes no deben inventarse. La limpieza puede normalizar vacíos, pero los indicadores omiten o muestran sin dato según el cálculo. Revisa cobertura antes de interpretar un KPI."),
    article("dates", "calidad", "Fechas y periodos", ["fecha incorrecta", "periodo", "mes", "ano", "año", "fecha texto"], "La plataforma intenta normalizar fechas reales y fechas escritas como texto. Si un periodo no aparece, revisa que su columna esté mapeada como fecha y que no mezcle formatos incompatibles o años de dos dígitos ambiguos."),
    article("sheet_public", "google_sheets", "Compartir Google Sheets", ["google sheets privado", "sheet privada", "compartir enlace", "hoja publica", "permiso google"], "Para conectar una hoja sin OAuth, en Google Sheets usa Compartir → Cualquier persona con el enlace → Lector. ADS Veris descarga únicamente la pestaña indicada por el enlace y no recibe tu contraseña de Google."),
    article("sheet_import", "google_sheets", "Conectar Google Sheets", ["conectar google sheets", "importar sheet", "pegar link", "enlace google"], "Ve a Conectores, pega la URL de la pestaña y elige Conectar. Cada enlace queda guardado como fuente y pasa por Estandarización y Limpieza igual que un Excel."),
    article("sheet_multiple", "google_sheets", "Varias hojas de Google", ["varias hojas google", "multiples links", "más de una sheet", "varias pestañas"], "Puedes registrar varios enlaces. Si son pestañas del mismo documento, abre cada pestaña y copia su URL con el gid correspondiente. ADS Veris las conserva como fuentes independientes para evitar mezclas silenciosas."),
    article("sheet_refresh", "google_sheets", "Actualizar Google Sheets", ["actualizar google sheets", "sincronizar", "cambios en sheet", "refrescar fuente"], "En Conectores usa Comprobar cambios o Actualizar. Al detectar una versión nueva, ADS Veris la vuelve a llevar por Estandarización y Limpieza; así un cambio remoto no reemplaza cálculos sin validación."),
    article("summary", "analisis", "Qué muestra Resumen", ["resumen", "dashboard", "vision del negocio", "tablero"], "Resumen es la vista ejecutiva: selecciona KPIs y gráficos compatibles con los campos realmente disponibles. Si falta una fuente necesaria, el indicador se omite en vez de estimarse con una variable distinta."),
    article("explore", "analisis", "Qué muestra Explorar datos", ["explorar datos", "diferencia resumen", "detalle", "profundizar"], "Explorar datos explica el resultado: permite elegir pregunta, rango, dimensión y métrica, muestra detalle mensual, hallazgos, cobertura y recomendaciones. Resumen responde qué pasó; Explorar ayuda a entender por qué."),
    article("sales_periods", "ventas", "Consolidar periodos de venta", ["periodos de venta", "unir ventas", "consolidar ventas", "ventas s1", "ventas s2"], "Consolidar períodos detecta hojas compatibles por estructura y rol comercial, no solo por llamarse Ventas. Apila todos los periodos válidos, conserva el origen y evita sumar hojas que no representan transacciones."),
    article("period_missing", "ventas", "Periodo no reconocido", ["falta periodo", "falta una hoja", "no reconoce venta", "no aparece una hoja", "menos periodos"], "Si falta un periodo, compara sus columnas con los otros: debe existir una fecha y un monto o cantidad comercial reconocible. Corrige el mapeo en Estandarización o revisa la hoja desde Administrar hojas; no se fuerza una unión insegura."),
    article("operating_cost", "finanzas", "Costo versus gasto operativo", ["costo operativo", "gasto operativo", "luz", "costos producto"], "Costo de venta y gasto operativo no son equivalentes. El costo de venta se vincula al producto vendido; arriendo, luz o administración son gastos operativos. ADS Veris solo muestra gastos operativos si existe una fuente identificable para ellos."),
    article("gross_margin", "finanzas", "Margen bruto", ["margen bruto", "utilidad bruta", "costo de venta"], "Margen bruto = (ventas netas − costo de venta atribuible) / ventas netas. Si una venta no tiene costo relacionado, la cobertura debe mostrarse y esa fila no puede tratarse como costo cero sin advertencia."),
    article("ebitda", "finanzas", "EBITDA", ["ebitda", "resultado operacional", "utilidad operacional"], "EBITDA necesita ingresos, costos y gastos operativos correctamente clasificados, además de excluir depreciación y amortización cuando estén disponibles. Si faltan esas fuentes, la plataforma no debe presentar EBITDA como calculado."),
    article("cashflow", "finanzas", "Flujo de caja", ["flujo de caja", "caja", "cobros", "pagos"], "Ventas y utilidad no equivalen a caja. Un flujo requiere fechas e importes de cobros y pagos o saldos de caja. Sin esas variables, ADS Veris evita inventar un flujo a partir de ventas."),
    article("currency", "finanzas", "Monedas mezcladas", ["moneda mixta", "moneda en uf", "monto en uf", "dolares", "pesos", "uf", "clp", "monedas incompatibles"], "No se suman monedas distintas sin tipo de cambio y fecha verificables. Si el archivo indica UF, ADS Veris conserva y muestra UF; si no declara otra unidad, prioriza pesos chilenos. Una conversión exige tipo de cambio y fecha verificables."),
    article("relationships", "relaciones", "Relacionar hojas", ["relacionar hojas", "conexiones", "clave comun", "join"], "Las relaciones seguras usan claves con cobertura, unicidad y cardinalidad medibles. Coincidir solo por el nombre de una columna no basta. En Relación manual puedes revisar la evidencia antes de activar una conexión."),
    article("cardinality", "relaciones", "Cardinalidad", ["cardinalidad", "muchos a uno", "1 a muchos", "muchos_a_1"], "Muchos a uno significa que varias filas de la tabla A apuntan a una fila única de B. Si la clave de B tiene duplicados, la unión puede multiplicar montos y debe bloquearse o advertirse."),
    article("coverage", "relaciones", "Cobertura de una relación", ["cobertura", "correspondencia", "sin match", "no relacionado"], "La cobertura indica qué porcentaje de filas encontró una clave correspondiente. Un 100% es ideal, pero también se revisan duplicados y cardinalidad: cobertura alta por sí sola no garantiza una unión segura."),
    article("blank_charts", "graficos", "Gráficos ausentes", ["grafico no aparece", "espacio blanco", "menos graficos", "dashboard desordenado"], "Los gráficos se eligen según los roles y la cobertura disponibles. Si falta la variable de un gráfico anterior, se reemplaza por otra visualización válida o se omite; nunca se completa con datos inventados. Los paneles usan una cuadrícula compacta para evitar huecos."),
    article("expand_chart", "graficos", "Ampliar y descargar gráficos", ["ampliar grafico", "ver grande", "descargar grafico", "exportar dashboard"], "Usa el botón de ampliar en la tarjeta para verla en una capa grande. Desde las acciones del dashboard puedes descargar una imagen o un HTML interactivo; el HTML conserva tooltips al pasar el mouse o tocar un punto."),
    article("html_chart", "graficos", "HTML interactivo", ["html", "tooltip", "mouse", "zoom rompe", "grafico descargado"], "El HTML exportado conserva la interacción original del gráfico. Para inspeccionar valores usa el mouse o toca un elemento en móvil; el zoom del navegador no es necesario y puede reducir el área útil."),
    article("history", "datos", "Historial", ["historial", "archivo anterior", "recuperar dataset", "restaurar"], "Historial conserva las cargas permitidas por tu plan y permite reabrir una versión procesada. Cada actualización de Google Sheets queda identificada como una nueva versión para no sobrescribir silenciosamente la anterior."),
    article("cache", "rendimiento", "Filtros sin repetir la limpieza", ["carga cada vez", "demora al volver", "demora filtro", "filtro demoraba", "por que demora el filtro", "filtro lento", "volver a filtrar", "vuelve a limpiar", "limpia todo", "cache", "ya estaba cargado"], "La limpieza completa se ejecuta cuando cambian el archivo, las reglas, el mapeo, la hoja o la decisión sobre duplicados. Los filtros del dashboard calculan sobre un artefacto limpio firmado y no vuelven a limpiar el Excel. Si la identidad no coincide o el artefacto no está disponible, el servidor descarta la caché y repite el proceso completo para mantener la corrección."),
    article("session", "cuenta", "Sesión vencida", ["sesion", "token vencido", "iniciar sesion", "401"], "Si tu sesión venció, guarda cualquier trabajo local y vuelve a iniciar sesión. La plataforma renueva credenciales automáticamente, pero una pestaña abierta durante mucho tiempo puede necesitar recarga."),
    article("plans", "planes", "Planes", ["plan basico", "plan analista", "plan gold", "diferencia planes"], "Básico cubre el flujo principal; Analista agrega descargas de base limpia y mayor capacidad operativa; Gold incluye los cupos más altos y conectores avanzados cuando estén disponibles. Revisa Planes para la matriz vigente."),
    article("trial", "planes", "Prueba gratuita", ["prueba gratis", "trial", "15 dias", "sin plan"], "La prueba permite conocer el flujo principal durante el periodo indicado en tu cuenta. El chat avanzado no se activa durante la prueba; el bot de Ayuda rápida y el soporte humano siguen disponibles."),
    article("coins", "ads_coins", "ADS Coins", ["ads coins", "monedas", "saldo", "comprar coins"], "ADS Coins será el saldo unificado para consumos variables. La billetera y su historial ya están preparados, pero las compras siguen deshabilitadas hasta integrar una pasarela. Nunca se descuenta una moneda sin registrar motivo y saldo resultante."),
    article("coin_uses", "ads_coins", "Usos futuros de ADS Coins", ["para que sirven monedas", "usos coins", "que comprar"], "Además del chat avanzado, los ADS Coins pueden cubrir limpiezas dirigidas adicionales, exportaciones pesadas, actualizaciones automáticas más frecuentes y conectores premium. Cada uso se activará por separado y mostrará el costo antes de confirmar."),
    article("advanced_chat", "asistente", "Chat avanzado", ["chat avanzado", "inteligencia artificial", "ia", "tokens"], "Chat avanzado está preparado para razonar sobre las métricas de tu negocio y consumirá ADS Coins según el plan. Por ahora permanece cerrado: Ayuda rápida responde dudas de uso sin IA y sin gastar monedas."),
    article("bot_metrics_scope_v2", "asistente", "Alcance de Ayuda rápida", ["bot no entiende", "respuesta automatica", "sin ia", "pregunta sobre mis numeros"], "Ayuda rápida usa reglas auditables: puede leer los indicadores publicados de tu archivo, explicar fórmulas y entregar conclusiones prudentes sin consumir ADS Coins. No inventa cifras ni calcula indicadores cuyas fuentes no estén disponibles.", priority=85),
    article("human_support", "soporte", "Hablar con soporte", ["hablar con persona", "soporte humano", "contactar admin", "necesito ayuda"], "Abre Ayuda en el menú, escribe tu caso y se creará una conversación con la cuenta administradora de ADS Veris. Puedes volver al mismo chat mientras siga abierto."),
    article("chat_expiry", "soporte", "Caducidad del chat", ["24 horas", "chat se elimina", "conversacion desaparece", "caduca"], "Por privacidad y orden, la conversación humana y sus mensajes se eliminan después de 24 horas sin actividad. Un nuevo mensaje antes del plazo reinicia el contador."),
    article("chat_closed", "soporte", "Conversación cerrada", ["conversacion cerrada", "cerraron chat", "volver a escribir"], "Cuando soporte cierra el caso verás Conversación cerrada y ya no podrás escribir en ese hilo. Si aparece una necesidad nueva, inicia otra conversación desde Ayuda."),
    article("privacy", "seguridad", "Privacidad", ["privacidad", "datos seguros", "contraseña", "quien ve mis datos"], "No escribas contraseñas ni secretos en soporte. Las conversaciones se asocian a tu cuenta, solo tú y la cuenta administradora pueden verlas, y se eliminan tras 24 horas sin actividad."),
    article("errors", "soporte", "Reportar un error", ["error", "falla", "no funciona", "ver detalle"], "Abre Ver detalle y copia el mensaje, luego indica en Ayuda qué acción realizabas, la página y el tipo de archivo. No envíes contraseñas ni datos personales; soporte ya recibe la ruta desde donde abriste el chat."),
    article("mobile", "uso", "Uso en celular", ["celular", "movil", "tocar grafico", "responsive"], "En móvil toca un punto o barra para ver su valor y usa el botón ampliar para ocupar la pantalla. Las tablas extensas permiten desplazamiento horizontal sin cortar el contenido."),
    article("reports", "exportacion", "Reportes y dashboard", ["reporte pdf", "exportar reporte", "exporto reporte", "descargar dashboard", "exportar resumen", "una sola plana"], "Las acciones de exportación generan una vista del dashboard actual. Antes de descargar selecciona hoja, periodo y filtros; esos criterios deben aparecer en el archivo para que el resultado sea auditable."),
    article("sales_formula", "ventas", "Ventas netas", ["ventas netas", "descuento", "ingreso neto", "formula ventas"], "Ventas netas se calcula desde el importe comercial disponible y los descuentos verificables. No se descuentan costos ni gastos en este indicador. La definición concreta se muestra en la tarjeta o en la información del cálculo."),
    article("inventory", "inventario", "Inventario", ["inventario", "stock", "rotacion", "movimiento inventario"], "Los movimientos de inventario necesitan producto, fecha, tipo de movimiento y cantidad. El stock final requiere un saldo inicial o una secuencia completa; si falta, ADS Veris muestra movimientos y no inventa existencias."),
    article("customers", "clientes", "Análisis de clientes", ["clientes", "concentracion cliente", "top clientes", "muchos clientes"], "Cuando existen muchos clientes, conviene mostrar participación, recurrencia, ticket y concentración por segmentos, no una lista masiva. Los clientes sin ID estable se agrupan solo si la etiqueta es consistente y se informa la cobertura."),
    article("forecast", "analisis", "Pronósticos", ["pronostico", "proyeccion", "predecir ventas", "forecast"], "Una proyección necesita suficiente historia y una frecuencia temporal consistente. Si el archivo no cumple esas condiciones, ADS Veris no debe presentar un pronóstico como hecho; puede mostrar tendencia observada y su cobertura."),
    article("current_ratio", "finanzas", "Liquidez corriente", ["liquidez corriente", "razon corriente", "indice de liquidez"], "Liquidez corriente = activo corriente / pasivo corriente. Mide cobertura contable de obligaciones de corto plazo. Debe compararse con periodos anteriores y con el sector: un valor alto también puede esconder inventario lento o recursos inmovilizados."),
    article("acid_test", "finanzas", "Prueba ácida", ["prueba acida", "test acido", "liquidez sin inventario"], "Prueba ácida = (activo corriente − inventarios) / pasivo corriente. Evalúa la capacidad de pago de corto plazo sin depender de vender inventario. Conviene revisar también la cobrabilidad y vencimiento de las cuentas por cobrar."),
    article("working_capital", "finanzas", "Capital de trabajo", ["capital de trabajo", "fondo de maniobra"], "Capital de trabajo = activo corriente − pasivo corriente. Un saldo positivo entrega holgura operativa, pero no garantiza caja disponible: importa la composición y velocidad de cobro, inventario y pago."),
    article("debt_ratio", "finanzas", "Endeudamiento", ["endeudamiento", "nivel de deuda", "pasivo sobre activo", "apalancamiento"], "El endeudamiento relaciona pasivos con activos o patrimonio, según la fórmula publicada. No existe un nivel universalmente correcto: revisa costo, plazo, moneda, capacidad de pago y estabilidad de los flujos antes de concluir."),
    article("interest_coverage", "finanzas", "Cobertura de intereses", ["cobertura de intereses", "puedo pagar intereses", "gastos financieros"], "Cobertura de intereses = resultado operativo / gastos financieros. Indica cuántas veces la operación cubre el costo financiero; debe leerse junto con vencimientos de capital y flujo de caja, no de forma aislada."),
    article("roa_roe", "finanzas", "ROA y ROE", ["roa", "roe", "rentabilidad activos", "rentabilidad patrimonio"], "ROA relaciona resultado con activos y ROE con patrimonio. Sirven para evaluar eficiencia y retorno del capital, pero el ROE puede subir por mayor deuda; compáralos juntos, con periodos equivalentes y promedios de balance cuando estén disponibles."),
    article("inventory_turnover", "finanzas", "Rotación de inventario", ["rotacion de inventario", "dias inventario", "stock inmovilizado"], "Rotación de inventario compara costo de ventas con inventario promedio. Una mayor rotación suele liberar capital, pero puede aumentar quiebres de stock; compárala con estacionalidad, margen y nivel de servicio."),
    article("collection_payment_days", "finanzas", "Días de cobro y pago", ["dias de cobro", "dias de pago", "ciclo de caja", "periodo medio"], "Los días de cobro estiman cuánto tarda el negocio en recuperar ventas a crédito y los días de pago cuánto tarda en pagar proveedores. La brecha entre ambos ayuda a anticipar presión de caja, siempre que fechas y saldos sean comparables."),
    article("financial_comparison", "finanzas", "Análisis horizontal y vertical", ["analisis horizontal", "analisis vertical", "comparar estados financieros"], "El análisis horizontal compara cambios entre periodos; el vertical expresa cada partida como porcentaje de una base, como ventas o activos. Úsalos juntos para distinguir crecimiento real, cambios de estructura y partidas atípicas."),
    article("npv_irr", "finanzas", "VAN y TIR", ["van", "tir", "valoracion de proyecto", "evaluar proyecto"], "El VAN descuenta los flujos esperados a una tasa exigida; un VAN positivo crea valor bajo esos supuestos. La TIR es la tasa que lleva el VAN a cero. Ambos dependen de flujos, horizonte y riesgo: conviene probar escenarios y no decidir solo por una TIR alta."),
    article("financial_quality", "calidad", "Errores en estados financieros", ["errores estados financieros", "balance descuadrado", "clasificacion contable", "datos financieros incorrectos"], "Antes de analizar, verifica que el balance cuadre, que periodos y unidades sean consistentes, que costos y gastos estén bien clasificados y que no falten movimientos. Una fórmula correcta sobre datos mal clasificados produce una conclusión engañosa."),
    article("treasury_budget", "finanzas", "Presupuesto de tesorería", ["presupuesto de tesoreria", "planificar caja", "falta de liquidez"], "Un presupuesto de tesorería ordena cobros y pagos por fecha para anticipar déficits o excedentes. Actualízalo con escenarios y desviaciones reales; ventas devengadas no sustituyen fechas efectivas de entrada y salida de caja."),
    article("financial_statements_set", "finanzas", "Estados financieros completos", ["estados financieros completos", "que estados necesito", "documentos financieros", "cuentas anuales"], "Un análisis completo combina estado de situación financiera, estado de resultados, estado de flujos de efectivo, estado de cambios en el patrimonio y sus notas. Cada documento responde una pregunta distinta; analizar solo ventas o caja deja fuera parte de la situación del negocio.", "¿Quieres que te explique qué aporta cada estado o qué columnas necesita ADS Veris?", 72),
    article("balance_sheet", "finanzas", "Estado de situación financiera", ["balance general", "estado de situacion financiera", "activos pasivos patrimonio", "que muestra el balance"], "El estado de situación financiera es una fotografía a una fecha: activos = pasivos + patrimonio. Sirve para revisar liquidez, estructura de deuda, capital de trabajo y recursos financiados por propietarios; no describe por sí solo el desempeño de todo un periodo.", "¿Quieres revisar liquidez, endeudamiento o capital de trabajo?", 70),
    article("income_statement", "finanzas", "Estado de resultados", ["estado de resultados", "perdidas y ganancias", "ingresos y gastos", "ingresos costos gastos", "resultado del periodo"], "El estado de resultados reúne ingresos, costos y gastos devengados durante un periodo para obtener utilidades o pérdidas. Devengado no significa cobrado o pagado: por eso una empresa puede mostrar utilidad y, aun así, enfrentar tensión de caja.", "¿Quieres distinguir margen bruto, resultado operativo y resultado neto?", 72),
    article("cash_flow_statement", "finanzas", "Estado de flujos de efectivo", ["estado de flujo de efectivo", "estado de flujos de efectivo", "actividades operacion inversion financiamiento"], "El estado de flujos de efectivo explica entradas y salidas reales separadas en operación, inversión y financiamiento. Permite evaluar capacidad de pago y necesidades de financiamiento; no debe reconstruirse desde ventas si faltan fechas efectivas de cobro y pago.", "¿Quieres que te indique los datos mínimos para calcularlo?", 74),
    article("equity_statement", "finanzas", "Cambios en el patrimonio", ["estado de cambios en el patrimonio", "cambios patrimonio", "utilidades retenidas", "dividendos patrimonio"], "El estado de cambios en el patrimonio explica aportes, resultados acumulados, reservas, dividendos y otras variaciones entre dos fechas. Ayuda a distinguir si el patrimonio creció por la operación, por nuevos aportes o por no distribuir utilidades.", "¿Quieres relacionarlo con ROE o con la política de dividendos?"),
    article("cashflow_structure", "finanzas", "Estructura del flujo de caja", ["estructura flujo de caja", "como preparar flujo de caja", "como preparo un flujo de caja", "saldo inicial ingresos egresos", "armar cash flow"], "Un flujo de caja parte del saldo inicial, ubica cobros y pagos en la fecha en que efectivamente ocurren, separa la operación del financiamiento y termina con el saldo final. El saldo final de un periodo pasa a ser el saldo inicial del siguiente.", "¿Quieres una lista de columnas para preparar esa proyección en Excel?", 76),
    article("operating_cashflow", "finanzas", "Flujo de caja operativo", ["flujo de caja operativo", "saldo operativo", "ingresos menos egresos operativos", "caja operativa"], "El flujo de caja operativo mide el efectivo generado por la actividad ordinaria antes de préstamos y amortizaciones. En una proyección básica es cobros operativos menos pagos operativos; debe analizarse aparte del dinero que entra por deuda o venta extraordinaria de activos.", "¿Quieres compararlo con utilidad operativa o con el saldo final de caja?", 73),
    article("cashflow_projection", "finanzas", "Proyectar flujo de caja", ["proyectar flujo de caja", "proyecto la caja", "proyeccion mensual de caja", "caja mensualmente", "flujo de caja proyectado", "escenarios de caja"], "Para proyectar caja, convierte presupuestos de ventas, cobranzas, compras, remuneraciones, gastos, impuestos e inversiones en fechas reales de cobro y pago. Trabaja por periodos concretos, documenta supuestos y compara escenarios; una venta a crédito pertenece al flujo cuando se cobra, no cuando se factura.", "¿Quieres que te ayude a ordenar los supuestos de cobro y pago?", 78),
    article("cashflow_shortfall", "finanzas", "Déficit de caja proyectado", ["deficit de caja", "saldo de caja negativo", "saldo queda negativo", "me faltara caja", "exceso de liquidez", "superavit de caja", "pido un prestamo", "pedir un prestamo"], "Un saldo proyectado bajo o negativo exige revisar primero supuestos de cobro, pagos postergables y gastos no esenciales. Después se evalúa financiamiento, considerando cuota, intereses y vencimientos. Un préstamo mejora caja inmediata, pero no mejora por sí mismo la generación operativa.", "¿Quieres priorizar las variables que más presionan tu caja?", 73),
    article("cash_ratio", "finanzas", "Ratio de efectivo", ["ratio de efectivo", "razon de efectivo", "liquidez inmediata", "efectivo sobre pasivo corriente"], "Ratio de efectivo = efectivo y equivalentes / pasivo corriente. Es la medida de liquidez más conservadora porque no depende de vender inventario ni cobrar cuentas; aun así, debe compararse con vencimientos, estacionalidad y necesidades operativas.", "¿Quieres compararlo con liquidez corriente y prueba ácida?", 70),
    article("liquidity_reading", "finanzas", "Cómo interpretar la liquidez", ["interpretar liquidez", "liquidez buena", "liquidez mala", "mejorar liquidez", "ratio mayor a uno"], "Una liquidez corriente sobre 1 indica cobertura contable de pasivos corrientes, pero no garantiza caja. Revisa tendencia, sector y composición: inventario lento o cuentas por cobrar vencidas pueden inflar el ratio. Conviene leerla junto con prueba ácida, efectivo, días de cobro y presupuesto de caja.", "¿Tienes activo corriente, inventario, efectivo y pasivo corriente para calcular las tres medidas?", 75),
    article("debt_structure", "finanzas", "Estructura del endeudamiento", ["endeudamiento total", "deuda a largo plazo", "endeudamiento patrimonial", "deuda sobre patrimonio", "estructura de deuda"], "El endeudamiento puede expresarse como deuda sobre activos, capital total o patrimonio. Además del porcentaje, revisa plazo, moneda, costo, garantías y capacidad de cubrir intereses y capital. Una deuda alta puede financiar crecimiento, pero eleva el riesgo si el flujo operativo es inestable.", "¿Quieres revisar deuda total, deuda de largo plazo o deuda sobre patrimonio?", 74),
    article("ratio_context", "finanzas", "Interpretar ratios con contexto", ["como interpretar ratios", "ratio bueno o malo", "valor ideal ratio", "comparar con industria"], "No existe un valor ideal universal para todos los ratios. Compara empresas del mismo sector, periodos equivalentes y la tendencia propia; luego explica el cambio con la composición de las cuentas. Un número aislado no demuestra mejora ni deterioro.", "¿Qué ratio y qué periodos quieres comparar?", 74),
    article("financial_analysis_process", "finanzas", "Proceso de análisis financiero", ["pasos analisis financiero", "como analizar estados financieros", "orden para analizar estados financieros", "interpretar estados financieros", "orden analisis financiero", "conclusion del negocio", "como cierro el analisis", "cerrar el analisis"], "Empieza validando que los estados estén completos y cuadren. Luego aplica análisis vertical y horizontal, calcula ratios pertinentes, grafica tendencias, compara con referentes similares y termina interpretando los resultados según el negocio y su entorno. La conclusión debe declarar datos faltantes y supuestos.", "¿Quieres comenzar por calidad, tendencias, estructura o ratios?", 77),
    article("projected_statements", "finanzas", "Estados financieros proyectados", ["estados financieros proyectados", "estado proforma", "proyeccion financiera", "presupuesto financiero"], "Los estados proyectados estiman una situación futura a partir de datos históricos, presupuestos y supuestos de gerencia. Sirven para anticipar resultados y necesidades, pero no son hechos: deben incluir horizonte, premisas, escenarios y revisiones periódicas contra lo realmente ocurrido.", "¿Quieres revisar los presupuestos que alimentan la proyección?", 72),
    article("projection_inputs", "finanzas", "Presupuestos para proyectar", ["presupuestos para proyectar", "que presupuestos necesito", "presupuestos necesito", "base de proyeccion", "premisas financieras", "supuestos proyeccion"], "Una proyección consistente suele conectar ventas y cobranzas, compras y pagos, remuneraciones, gastos, impuestos, inversiones y financiamiento. Esas piezas deben compartir periodo, moneda y políticas de crédito; si cambias una premisa, actualiza resultados, balance y caja.", "¿Quieres construir un escenario base, optimista y conservador?", 70),
    article("time_value", "finanzas", "Valor del dinero en el tiempo", ["valor del dinero en el tiempo", "valor presente", "valor futuro", "tasa de descuento"], "El dinero de hoy y el de una fecha futura no son equivalentes. El valor presente descuenta flujos futuros por tiempo y riesgo; el valor futuro capitaliza un monto actual. La tasa y la periodicidad deben corresponder al mismo horizonte para evitar resultados engañosos.", "¿Quieres calcular valor presente, valor futuro o evaluar un proyecto?", 69),
    article("simple_compound_interest", "finanzas", "Interés simple y compuesto", ["interes simple", "interes compuesto", "interes sobre intereses", "capitalizacion compuesta"], "El interés simple se calcula siempre sobre el capital inicial. El compuesto incorpora los intereses acumulados a la base del periodo siguiente. Antes de compararlos, iguala tasa, periodicidad, plazo, comisiones y moneda.", "¿Quieres que te muestre las fórmulas con tus datos?", 67),
    article("financial_risk", "finanzas", "Riesgo financiero", ["riesgo financiero", "riesgo de liquidez", "riesgo de credito", "riesgo cambiario", "riesgo de tasa"], "El riesgo financiero incluye, entre otros, liquidez, crédito, tasa de interés, mercado y moneda. Para evaluarlo identifica exposición, probabilidad, impacto y capacidad de respuesta; una rentabilidad esperada mayor no elimina el riesgo asumido.", "¿Qué exposición quieres revisar primero?"),
    article("profitability", "finanzas", "Rentabilidad", ["rentabilidad", "rentabilidad del negocio", "negocio rentable", "retorno del negocio"], "La rentabilidad relaciona el resultado obtenido con una base comparable, como ventas, activos o patrimonio. No es lo mismo que ingresos ni caja: identifica primero qué resultado y qué inversión se usan, compara periodos equivalentes y revisa el efecto de la deuda.", "¿Quieres analizar margen sobre ventas, ROA o ROE?", 68),
    article("dashboard_filters", "analisis", "Filtros activos", ["filtros activos", "que filtros hay", "alcance del dashboard", "filtrar resumen"], "Los filtros del Resumen definen el alcance común de todos los KPI y gráficos. El bot recibe las métricas ya filtradas y debe mencionar ese alcance; si estás fuera del Resumen, abre el dataset para consultar sus valores actuales.", "¿Quieres filtrar por periodo, equipo, categoría, canal u otra dimensión disponible?", 71),
    article("collection_total_concept", "finanzas", "Cobranza total", ["cobranza total", "recaudacion total", "total cobrado", "cobranza por equipo"], "La recaudación o cobranza total suma los pagos incluidos por la definición y los filtros visibles. No equivale necesariamente a ventas, utilidad ni saldo de caja. Para explicarla por equipo, cada participación debe usar el mismo total como denominador.", "Abre Resumen y pregúntame por el total o por un equipo para usar tus cifras visibles.", 69),
    article("collection_participation", "graficos", "Participación de cobranza por equipo", ["participacion en cobranza por equipo", "participacion cobranza equipo", "aporte de cada equipo"], "La participación por equipo divide la cobranza atribuida a cada equipo por la cobranza total visible. Las participaciones deben sumar aproximadamente 100%, salvo redondeo, y reaccionar a los mismos filtros del dashboard.", "¿Quieres identificar el equipo líder o comparar dos equipos?", 72),
]


def normalize(text: str) -> str:
    return normalize_basic(text)


def rank_articles(message: str, articles: list[dict[str, Any]] | None = None) -> list[tuple[float, dict[str, Any]]]:
    normalized = normalize_query(message)
    padded = f" {normalized} "
    words = set(normalized.split())
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in articles or ARTICLES:
        trigger_scores: list[float] = []
        for trigger in item.get("triggers") or []:
            trigger_norm = normalize(str(trigger))
            if not trigger_norm:
                continue
            # Match complete words/phrases. Short triggers such as "ia" used
            # to fire inside unrelated words like "limpiar" and displaced the
            # correct operational answer.
            if f" {trigger_norm} " in padded:
                trigger_scores.append(8 + len(trigger_norm.split()) * 2)
            else:
                trigger_words = set(trigger_norm.split())
                if trigger_words:
                    trigger_scores.append(4 * len(words & trigger_words) / len(trigger_words))
        # Los triggers de un articulo son sinonimos, no evidencia acumulable.
        # Usar el mejor evita que una entrada generica con muchos sinonimos
        # desplace a una frase exacta y mas especifica.
        score = max(trigger_scores, default=0.0)
        title_words = set(normalize(str(item.get("title") or "")).split())
        score += 2 * len(words & title_words)
        score += min(int(item.get("priority") or 0), 100) / 100
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


def answer_for(
    message: str,
    articles: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metric_answer = answer_metrics_question(message, metrics, history)
    if metric_answer is not None:
        return metric_answer
    catalog = articles or ARTICLES
    normalized = normalize_query(message)
    contextual_markers = (
        "y eso",
        "eso es bueno",
        "como lo interpreto",
        "como se interpreta",
        "como lo mejoro",
        "que necesito para calcularlo",
        "que datos necesito para calcularlos",
        "eso es malo",
        "como lo proyecto",
        "en que orden",
        "que significa ese ratio",
        "y como se calcula",
    )
    previous = next(
        (
            str(item.get("content") or "")
            for item in reversed(history or [])
            if item.get("role") == "user" and str(item.get("content") or "").strip()
        ),
        "",
    )
    if previous and "en que orden" in normalized:
        ranking_message = "orden para analizar estados financieros"
    elif previous and "como lo proyecto" in normalized:
        ranking_message = f"{previous} proyectar flujo de caja"
    else:
        ranking_message = (
            f"{previous} {message}"
            if previous and (normalized.startswith("y ") or any(marker in normalized for marker in contextual_markers))
            else message
        )
    ranked = rank_articles(ranking_message, catalog)
    if not ranked or ranked[0][0] < 3.5:
        suggestions = [item["title"] for item in sorted(catalog, key=lambda row: row.get("priority", 0), reverse=True)[:4]]
        return {
            "answer": "Puedo leer los indicadores visibles de tu archivo y orientarte sobre importación, limpieza, Google Sheets, finanzas, relaciones, gráficos, planes, ADS Coins y soporte. Pregunta por una cifra o usa el nombre del indicador. Si una fuente no está disponible, te diré qué falta en vez de estimarla; para un caso no cubierto también puedes abrir Ayuda y conversar con soporte humano.",
            "matched_key": None,
            "confidence": "low",
            "suggestions": suggestions,
        }
    score, best = ranked[0]
    related = [
        row[1]["title"] for row in ranked[1:]
        if row[1].get("category") == best.get("category")
    ][:3]
    return {
        "answer": f"{best['response']}\n\n{best.get('follow_up') or ''}".strip(),
        "matched_key": best["key"],
        "confidence": "high" if score >= 10 else "medium",
        "suggestions": related,
    }
