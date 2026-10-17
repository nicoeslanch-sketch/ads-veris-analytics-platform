"""Conversations about observed seasonality, with no invented forecasts."""

import re
import math

from .language_normalization import normalize_query

MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
TOPIC = r'estacional|temporada|pico.*(?:repet|recurrent)|(?:cada|todos los).*ano|(?:solo|solamente|cada)\s+(?:en\s+)?(?:' + '|'.join(MONTHS) + ')'


def answer_product_patterns(message, metrics, history=None):
    q = normalize_query(message)
    previous_questions = [normalize_query(row.get('content', '')) for row in reversed(history or []) if row.get('role') == 'user']
    previous = previous_questions[0] if previous_questions else ''
    for candidate in previous_questions[:4]:
        if re.search(TOPIC, candidate):
            previous = candidate
            break
        if not re.search(r'^(y |en |entonces|que hago|debo|deberia)', candidate):
            break
    followup = bool(re.search(TOPIC, previous) and re.search(r'^(y |en |entonces|que hago|debo|deberia)', q)
                    and re.search(r'reponer|comprar|invertir|marketing|retirar|dejar|temporada|producto|20\d{2}|ano|hago|' + '|'.join(MONTHS), q))
    if not re.search(TOPIC, q) and not followup:
        return None
    def reply(text, key, confidence='medium'):
        return {'answer': text, 'matched_key': 'metric_product_patterns_' + key, 'confidence': confidence,
                'source': 'metrics', 'suggestions': ['Productos sin ventas', 'Producto mas rentable', 'Como elegir un grafico']}
    ledger = (metrics.get('analisis_negocio') or {}).get('conciliacion')
    patterns = ledger.get('patrones_productos') if isinstance(ledger, dict) and ledger.get('available') else metrics.get('patrones_productos') if not metrics.get('analisis_negocio') else None
    if not isinstance(patterns, dict):
        return reply('No tengo evidencia por ID de picos recurrentes en anos comparables para este alcance. Un mes alto no demuestra estacionalidad. Revisa fechas, identificadores y al menos dos anos con doce meses observados; un ranking total no permite reconstruir ese historial.', 'missing')
    if re.search(r'proximo|predic|pronostic|garantiz|seguro', q):
        return reply('Un pico historico repetido no garantiza que vuelva a ocurrir. Para planificar compras contrasta margen, stock, plazos y campanas; cualquier cifra futura requiere supuestos explicitos y no es una venta observada.', 'forecast')
    if followup and re.search(r'reponer|comprar|invertir|marketing|retirar|dejar|hago', q):
        return reply('No recomiendo retirar ni aumentar compras automaticamente. Comprueba la temporada observada por ID, margen, disponibilidad y plazos. Si la pausa ocurre fuera del mes de mayor actividad, considera reposicion gradual antes de esa temporada y una prueba acotada de marketing; compara resultados antes de reinvertir.', 'decision')
    def valid_peak(row):
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('nombre'), str):
            return False
        month = row.get('mes')
        evidence = row.get('evidencia')
        return (isinstance(month, int) and 1 <= month <= 12 and isinstance(evidence, list) and len(evidence) >= 2
                and all(isinstance(item, dict) and re.fullmatch(r'\d{4}', str(item.get('ano', '')))
                        and item.get('mes') == month and isinstance(item.get('participacion_pct'), (int, float))
                        and math.isfinite(item['participacion_pct']) and 30 <= item['participacion_pct'] <= 100
                        for item in evidence)
                and len({str(item['ano']) for item in evidence}) == len(evidence))
    raw_peaks = patterns.get('picos_recurrentes') or []
    rows = [row for row in raw_peaks if valid_peak(row)] if isinstance(raw_peaks, list) else []
    requested_years = set(re.findall(r'\b20\d{2}\b', q))
    years = patterns.get('anos_comparables') or []
    valid_years = {year for year in years if isinstance(year, str) and re.fullmatch(r'\d{4}', year)} if isinstance(years, list) else set()
    if requested_years and not requested_years.issubset(valid_years):
        return reply('Ese ano no tiene doce meses comparables en la evidencia disponible. Cambia el alcance o completa la fuente antes de evaluar estacionalidad; no sustituire ese periodo por otro.', 'year_scope')
    requested = next((i for i, month in enumerate(MONTHS, 1) if re.search(r'\b' + month + r'\b', q)), None)
    if requested:
        rows = [row for row in rows if row.get('mes') == requested]
    # Do not substitute the first ranked product for a named product or ID.
    named = []
    lookup = previous + ' ' + q if followup and not re.search(r'\b(producto|sku|id)\b', q) else q
    for row in [*(patterns.get('series') or []), *rows]:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            continue
        name = normalize_query(row.get('nombre', ''))
        if (name and re.search(r'\b' + re.escape(name) + r'\b', lookup)
                or re.search(r'\bid\s+' + re.escape(str(row.get('id'))) + r'\b', lookup, re.I)):
            named.append(row)
    if named:
        rows = [row for row in rows if row.get('id') in {item.get('id') for item in named}]
    elif re.search(r'(?:producto|sku|id)\s+(?!tiene|con|por|es|son|se|de|mas|menos|en|que)([a-z0-9]+)', q):
        return reply('No puedo identificar con certeza ese producto en las series disponibles. Indica su ID exacto o revisa el Calendario de productos en Explorar; no usare otro producto como sustituto.', 'product_scope')
    if not rows:
        return reply('No se detecto un pico recurrente que cumpla el criterio en los productos y meses consultados. Esto no descarta estacionalidad: pueden faltar anos comparables o existir un patron menos concentrado. No infiero ausencia de ventas de un ranking recortado.', 'none')
    evidence = []
    for row in rows[:3]:
        years = ', '.join(str(item['ano']) for item in row['evidencia'])
        shares = ', '.join(f"{item['ano']}: {item['participacion_pct']}%" for item in row['evidencia'])
        evidence.append(f"{row['nombre']} (ID {row['id']}): pico en {MONTHS[row['mes'] - 1]} en {years} ({shares} de sus ventas positivas anuales)")
    return reply('; '.join(evidence) + '. El criterio exige el mismo mes con al menos 30% de ventas positivas en cada ano comparable. Excluye devoluciones de esa base; no demuestra la causa ni predice el futuro. Comprueba cobertura, stock, margen y campanas antes de ajustar reposicion.', 'observed', 'high')
