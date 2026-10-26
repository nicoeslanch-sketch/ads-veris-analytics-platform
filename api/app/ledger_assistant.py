"""Deterministic answers from the reconciled ledger, never legacy estimates."""
import math
import re

from .language_normalization import normalize_basic, normalize_query
from .metric_assistant import format_amount


SUGGESTIONS = ['Ventas netas', 'Resultado antes de impuestos', 'Producto mas rentable', 'Productos sin ventas']
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
FIELDS = (
    (r'antes.*devolucion|ventas brutas|ventas emitidas', 'ventas_emitidas_netas', 'Ventas emitidas netas antes de devoluciones', 'money'),
    (r'cuentas? por cobrar|\bcxc\b|me deben', 'cuentas_por_cobrar', 'Cuentas por cobrar al cierre', 'money'),
    (r'cuentas? por pagar|\bcxp\b|debo a proveedores', 'cuentas_por_pagar', 'Cuentas por pagar al cierre', 'money'),
    (r'flujo|caja', 'flujo_caja_antes_iva', 'Flujo antes de liquidacion de IVA', 'money'),
    (r'deposit|cobros netos', 'depositos_netos', 'Depositos netos', 'money'),
    (r'iva.*credito', 'iva_credito', 'IVA credito observado', 'money'),
    (r'iva', 'iva_debito_neto', 'IVA debito neto', 'money'),
    (r'notas? de credito|notas? credito|devolucion', 'notas_credito_netas', 'Notas de credito netas', 'money'),
    (r'anulad', 'ventas_anuladas', 'Ventas anuladas', 'count'),
    (r'cuantas ventas|numero de ventas|documentos emitidos|transacciones', 'ventas_emitidas', 'Documentos de venta emitidos', 'count'),
    (r'lineas.*emitidas', 'lineas_emitidas', 'Lineas de ventas emitidas', 'count'),
    (r'lineas|detalles de venta', 'lineas_fisicas', 'Lineas fisicas de todo el archivo, incluidas anuladas', 'count'),
    (r'clientes|compradores', 'clientes_compradores', 'Clientes compradores unicos', 'count'),
    (r'compras', 'compras_netas', 'Compras netas de inventario', 'money'),
    (r'comision', 'comisiones_cobro', 'Comisiones de cobro', 'money'),
    (r'nomina|sueldo|remuneracion', 'nominas', 'Costo de nominas', 'money'),
    (r'intereses', 'intereses_pagados', 'Intereses pagados', 'money'),
    (r'gasto', 'gastos_operacionales_netos', 'Gastos operacionales netos', 'money'),
    (r'costo', 'costo_ventas_neto', 'Costo de ventas neto', 'money'),
    (r'resultado|antes de impuestos|utilidad neta|ganancia neta', 'resultado_antes_impuestos', 'Resultado antes de impuestos', 'money'),
    (r'margen', 'margen_bruto_pct', 'Margen bruto', 'percent'),
    (r'utilidad|ganancia|beneficio', 'utilidad_bruta', 'Utilidad bruta', 'money'),
    (r'inventario.*valor|valor.*inventario', 'inventario_valorizado', 'Inventario valorizado al costo del lote', 'money'),
    (r'inventario|stock', 'stock_unidades', 'Unidades en inventario al cierre', 'count'),
    (r'unidades|cantidad vendida', 'unidades_emitidas', 'Unidades en ventas emitidas, antes de devoluciones', 'count'),
    (r'ingreso|ventas|vendi|facturacion', 'ventas_netas', 'Ventas netas despues de notas de credito', 'money'),
)


def answer_ledger(message, ledger, history=None):
    q = normalize_query(message)
    def reply(text, key='value', confidence='high'):
        return {'answer': text, 'matched_key': 'metric_ledger_' + key, 'confidence': confidence,
                'suggestions': SUGGESTIONS, 'source': 'metrics'}
    if re.search(r'\b(plan|coins|suscripcion|password|contrasena|soporte|humano|descargar|exportar|limpieza|estandarizar)\b', q):
        return None
    if re.search(r'\b(que es|definicion|formula|como se calcula)\b', q):
        return None
    if q in ('gracias', 'muchas gracias', 'ok gracias'):
        return reply('De nada. Las respuestas usan los datos y el periodo visible, sin completar cifras ausentes.', 'thanks')
    previous_questions = [normalize_query(row.get('content', '')) for row in reversed(history or []) if row.get('role') == 'user']
    previous = next((text for text in previous_questions if any(re.search(pattern, text) for pattern, *_ in FIELDS)
                     or re.search(r'producto|sucursal|categoria|mes|negocio', text)), '')
    new_metric = any(re.search(pattern, q) for pattern, *_ in FIELDS) or bool(re.search(r'\b(?:categoria|producto|sucursal)\b', q))
    if re.match(r'^(y |en |del |durante |ese |esa |esos |esas |por que|que hago|entonces)', q) and previous and not new_metric:
        if re.search(r'\b20\d{2}\b', q):
            previous = re.sub(r'\b(?:20\d{2}|' + '|'.join(MONTHS) + r')\b', '', previous)
        q = previous + ' ' + q
    business_question = bool(re.search(r'ingreso|venta|vendi|costo|gasto|utilidad|ganancia|margen|producto|inventario|stock|caja|cobro|pagar|credito|iva|resultado|nomina|sueldo|sucursal|categoria|mes|resumen|conclusion|negocio|liquidez|endeudamiento|rentab|deposito|comision|datos|cuanto|periodo|saldo|banco|ticket|\bcxc\b|\bcxp\b', q))
    if not business_question and not any(re.search(pattern, q) for pattern, *_ in FIELDS):
        return None
    if not ledger.get('available'):
        warnings = '; '.join(str(item) for item in (ledger.get('advertencias') or [])[:3])
        return reply('La conciliacion esta bloqueada: ' + warnings + '. No usare estimaciones anteriores para contestar.', 'blocked', 'medium')
    k = ledger.get('kpis') or {}
    period = ledger.get('periodo') or {}
    scope = f" Periodo: {period.get('desde')} a {period.get('hasta')}."
    currency = ledger.get('moneda') or 'CLP'
    def number(value, unit='money'):
        if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
            return 'no disponible'
        if unit == 'money':
            return format_amount(value, currency)
        text = f'{value:,.2f}'.rstrip('0').rstrip('.').replace(',', '_').replace('.', ',').replace('_', '.')
        return text + ('%' if unit == 'percent' else '')
    if re.search(r'saldo bancario|dinero.*banco|saldo.*banco|liquidez|endeudamiento|\broa\b|\broe\b', q):
        return reply('Este libro no contiene un balance completo ni un saldo bancario inicial conciliado. No puedo deducir liquidez, ROA, ROE o saldo de banco a partir de ventas y cobros solamente.', 'balance_missing', 'medium')
    if re.search(r'convert|pasar.*uf', q):
        return reply('No convierto importes sin una tasa y fecha aplicable. El archivo mantiene su moneda: ' + currency + '.', 'conversion', 'medium')
    if re.search(r'moneda|en pesos|en uf|divisa', q):
        return reply('La conciliacion esta expresada en ' + currency + '. No se mezclan monedas ni se inventa un tipo de cambio.', 'currency')
    years = re.findall(r'\b20\d{2}\b', q)
    mentioned_months = [i + 1 for i, name in enumerate(MONTHS) if re.search(r'\b' + name + r'\b', q)]
    explicit_period = bool(years or mentioned_months or re.search(r'\bhoy|ayer|semana|trimestre\b', q))
    literal = normalize_basic(message)
    named_groups = {}
    for group_key in ('productos', 'sucursales', 'categorias'):
        matches = [row for row in ledger.get(group_key) or [] if any(
            normalize_basic(row.get(key) or '') and re.search(
                r'\b' + re.escape(normalize_basic(row[key])) + r'\b', literal)
            for key in ('nombre', 'id'))]
        if matches:
            named_groups[group_key] = matches
    month_rank = bool(re.search(r'\bmes\b', q) and re.search(r'\b(?:mejor|peor|mas|menos|mayor|menor)\b', q))
    if (explicit_period or month_rank) and (named_groups or re.search(r'\b(?:producto|categoria|sucursal)\b', q)):
        return reply('No tengo publicado ese cruce entre segmento y periodo en la conciliacion. '
                     'Aplica el filtro de fechas y el de segmento; el total mensual del negocio no sustituye al segmento.' + scope,
                     'cross_scope', 'medium')
    if re.search(r'\b(?:unidades|cantidad vendida)\b', q) and re.search(r'devolucion|signo', q):
        if explicit_period or named_groups or re.search(r'\b(?:producto|categoria|sucursal)\b', q):
            return reply('Para explicar las unidades y devoluciones de ese segmento o periodo, selecciona '
                         'ese alcance. No sustituyo su desglose por el total del libro.' + scope, 'units_scope', 'medium')
        return reply('El indicador de unidades emitidas es ' + number(k.get('unidades_emitidas'), 'count') +
                     ': corresponde a ventas emitidas antes de devoluciones, no a unidades netas. '
                     'En esta conciliacion las devoluciones se vinculan por ID y fecha de nota de credito; '
                     'los rankings indican por separado las unidades netas de devoluciones. '
                     'No se debe cambiar el signo de las cantidades del Excel sin revisar su definicion.' + scope,
                     'units_returns')
    if re.search(r'\b(?:utilidad|resultado|ganancia|margen)\b', q) and re.search(r'\b(?:operacional|operativo|operativa)\b', q):
        return reply('No hay un resultado operacional publicado por separado en esta conciliacion. '
                     'La utilidad bruta y el resultado antes de impuestos son medidas distintas; '
                     'este ultimo tambien descuenta intereses, por lo que no lo renombro como operacional.' + scope,
                     'operational_missing', 'medium')
    field = next(((key, label, unit) for pattern, key, label, unit in FIELDS if re.search(pattern, q)), None)
    if re.search(r'cuantas ventas emitidas|numero.*ventas emitidas', q):
        field = ('ventas_emitidas', 'Documentos de venta emitidos', 'count')
    if explicit_period:
        monthly_field = {'ventas_netas': 'ventas', 'costo_ventas_neto': 'costo', 'utilidad_bruta': 'utilidad'}
        if field and field[0] in monthly_field and len(set(years)) == 1 and len(mentioned_months) <= 1 and not re.search(r'producto|sucursal|categoria|trimestre|semana|hoy|ayer|compar', q):
            prefix = years[0] + (f'-{mentioned_months[0]:02d}' if mentioned_months else '')
            rows = [row for row in ledger.get('mensual', []) if str(row.get('mes', '')).startswith(prefix)]
            if rows:
                value = sum(row.get(monthly_field[field[0]], 0) for row in rows)
                return reply(f'{field[1]} en {prefix}: {number(value)}. Solo incluye los meses disponibles dentro del filtro actual.' + scope, 'period_value')
        return reply('Para ese periodo o comparacion cambia el filtro de fechas del dashboard. No sustituire una cifra mensual, anual o de un segmento por el total del archivo.' + scope, 'period_filter', 'medium')
    if re.search(r'sin ventas|sin vender|no se vende|estancad|reinvert|marketing|retiro|retirar|que hago', q):
        rows = ledger.get('inventario_lento') or []
        evidence = '; '.join(f"{row['nombre']}: {number(row.get('valor'))} en stock, " + (f"{number(row.get('dias_sin_venta'), 'count')} dias sin venta observada" if row.get('dias_sin_venta') is not None else 'sin ventas observadas') for row in rows[:3])
        if not evidence:
            evidence = 'No se detecto stock con 90 o mas dias sin ventas observadas'
        return reply(evidence + '. Antes de reducir compras, comprueba estacionalidad, disponibilidad y margen. Prueba ajustes acotados de precio, presentacion o marketing; el archivo no demuestra la causa de la baja.' + scope, 'slow_inventory')
    group = next((key for word, key in [('producto', 'productos'), ('sucursal', 'sucursales'), ('categoria', 'categorias')] if word in q), None)
    if group is None and len(named_groups) == 1:
        group = next(iter(named_groups))
    if len(named_groups) > 1:
        return reply('Hay varios segmentos o dimensiones en la pregunta. Sus totales no permiten '
                     'deducir la interseccion; indica una sola dimension o aplica el cruce en Explorar.' + scope,
                     'group_ambiguous', 'medium')
    if group:
        rows = ledger.get(group) or []
        measure = 'utilidad' if re.search(r'rentab|utilidad|ganancia|beneficio', q) else 'unidades' if 'unidades' in q else 'ventas'
        mentioned = named_groups.get(group, [])
        if mentioned and measure == 'ventas' and re.search(r'\b(?:suma|sumar|suman|juntos|juntas)\b', q):
            from .metric_assistant import _group_answer
            result = _group_answer({'moneda': currency},
                                   [{'nombre': row.get('nombre'), 'ingresos': row.get('ventas')} for row in rows],
                                   {'productos': 'producto', 'categorias': 'categoria', 'sucursales': 'sucursal'}[group],
                                   'metric_ledger_group', literal)
            result['answer'] += ' La medida es ventas netas de devoluciones.' + scope
            return result
        if mentioned:
            rows = mentioned
        elif not re.search(r'mas|menos|mejor|peor|principal|top|ranking|lider', q):
            return reply('Indica el nombre del producto, sucursal o categoria, o pide un ranking por ventas, unidades o utilidad. No tengo publicada cualquier combinacion de segmentos.', 'group_clarify', 'medium')
        rows = sorted(rows, key=lambda row: row.get(measure, 0), reverse=not bool(re.search(r'menos|peor', q)))
        label = {'ventas': 'ventas netas', 'utilidad': 'utilidad bruta', 'unidades': 'unidades netas de devoluciones'}[measure]
        evidence = '; '.join(f"{row['nombre']}: {number(row.get(measure), 'count' if measure == 'unidades' else 'money')}" for row in rows[:3])
        return reply(f'{label.capitalize()}: {evidence or "sin grupos disponibles"}. La utilidad bruta no distribuye gastos generales por producto.' + scope, 'ranking')
    if re.search(r'\b(mejor mes|peor mes|tendencia|evolucion|mes.*mas|mes.*menos)\b', q):
        rows = ledger.get('mensual') or []
        if not rows:
            return reply('No hay meses comparables en el filtro actual.', 'trend_missing', 'medium')
        best = min(rows, key=lambda row: row['ventas']) if re.search(r'peor|menos', q) else max(rows, key=lambda row: row['ventas'])
        return reply(f"El mes con {'menores' if re.search(r'peor|menos', q) else 'mayores'} ventas netas observadas es {best['mes']}: {number(best['ventas'])}. Compara meses completos y considera estacionalidad; esto no explica por si solo la causa." + scope, 'trend')
    if re.search(r'conclusion|resume|resumen|negocio|que opinas|que deberia', q):
        return reply(f"Ventas netas: {number(k.get('ventas_netas'))}; utilidad bruta: {number(k.get('utilidad_bruta'))}; resultado antes de impuestos: {number(k.get('resultado_antes_impuestos'))}. " +
            ('El margen comercial no cubre todos los gastos observados. Revisa nominas, gastos y comisiones junto con precios y volumen; no confundas ventas con caja.' if (k.get('resultado_antes_impuestos') or 0) < 0 else 'Contrasta rentabilidad, cobros pendientes e inventario antes de aumentar compras.') + scope, 'overview')
    if re.search(r'ticket|promedio.*venta', q):
        value = k.get('ventas_emitidas_netas', 0) / k['ventas_emitidas'] if k.get('ventas_emitidas') else None
        return reply('Ticket por documento emitido, neto de IVA y antes de notas de credito: ' + number(value) + scope, 'ticket')
    if field:
        key, label, unit = field
        extra = ''
        if key == 'resultado_antes_impuestos':
            extra = ' Es utilidad bruta menos gastos, nominas, comisiones e intereses; no es utilidad despues de impuestos.'
        elif key == 'utilidad_bruta':
            extra = ' Es ventas netas menos costo de ventas, antes de gastos generales e impuestos.'
        elif key == 'flujo_caja_antes_iva':
            extra = ' Incluye desembolsos y pagos de prestamos; no es saldo bancario.'
        elif key == 'compras_netas':
            extra = ' Comprar inventario no equivale a reconocer todo ese importe como gasto del periodo.'
        elif key in ('cuentas_por_cobrar', 'cuentas_por_pagar', 'stock_unidades', 'inventario_valorizado'):
            extra = ' Es acumulado hasta el cierre, incluyendo movimientos anteriores al inicio del filtro.'
        return reply(f'{label}: {number(k.get(key), unit)}.' + extra + scope, key)
    return reply('No tengo publicado ese indicador o cruce en la conciliacion actual. Puedo responder ventas netas, costo historico, utilidad, cobros, inventario y rankings respaldados por IDs.' + scope, 'unsupported', 'medium')
