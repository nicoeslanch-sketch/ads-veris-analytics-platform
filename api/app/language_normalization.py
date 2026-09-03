"""Normalizacion tolerante para preguntas en espanol sobre datos y finanzas.

El motor conserva los identificadores desconocidos (clientes, productos o equipos)
y solo corrige palabras pertenecientes a un vocabulario controlado. Tambien separa
consultas escritas sin espacios, por ejemplo ``cuantossonmisingresostotales``.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache


def normalize_basic(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text).casefold())
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


# Vocabulario funcional, financiero, comercial y propio de ADS Veris. Las palabras
# se almacenan sin tildes porque normalize_basic se ejecuta antes de consultarlas.
_VOCABULARY = frozenset(
    """
    a acerca activo activos actual actuales administracion administrativo agencia
    agencias ahorro al alerta alertas ampliar analiza analisis analizar anterior anteriores ano anos
    apalancamiento aplicar aporte aportan aporta aporto archivo archivos asignar asistente
    auditoria balance bancario beneficio beneficios bruto bruta caja calcular calculo
    calidad cambio cambios canal canales capital categoria categorias cierre cliente
    clientes cobrar cobranza cobranzas cobro cobros cobertura compara comparar comparacion comparalos comparalas
    compuesto consolidado consolidar contabilidad contable contado contexto conversion
    convertir convertirlo corriente corto costo costos credito creditos cual cuales cuando cuanto
    cuantos dato datos debe deuda deudas diferencia dinero documento documentos donde
    duplicado duplicados efectivo eficiencia egreso egresos el eliminar en
    endeudamiento entrada entradas equipo equipos error errores es estado estados
    estandarizacion estandarizar estructura evolucion excel excedente excedentes
    explicar exportar exporto falta faltan fecha fechas financiacion financiamiento financiero
    financieros finanzas flujo flujos forma formas formula ganancia ganancias gasto gastos generar general grafico graficos
    horizontal hoja hojas hoy id importe importacion importar impuesto impuestos
    indicador indicadores industria informacion ingreso ingresos interes intereses inventario
    inversion inversiones largo liquidez limpiar limpieza lo los margen margenes mayor
    mejor mejores menor mes meses mi mis moneda monedas monto montos movimiento
    movimientos negocio neta netas neto nivel nombre notas obligacion obligaciones
    operativo operativos pago pagos patrimonio periodo periodos peor perdida perdidas
    pesos plazo por porcentaje porciones presupuesto presupuestos prestamo prestamos primero primeros producto productos
    promedio proyectado proyectados proyeccion proyectar proveedor proveedores prueba publica privada
    que quiero ratio ratios razon recaudacion recomendacion recomendaciones registro
    registros relacion rentabilidad reporte reportes resultado resultados resumen riesgo
    riesgos roa roe saldo saldos semana semanas servicio servicios sin situacion
    sobre solvencia stock sucursal sucursales tasa tasas temporal tendencia tiene tengo
    tesoreria tiempo tipo total totales transaccion transacciones uf ultima ultimo
    unidad unidades utilidad utilidades valor valores van venta ventas vertical vs
    y ya yo acid acid-test acida buena bueno cashflow celular dashboard deficit descargo descargar empiezo exploracion explorar
    filtro filtros funciona grafica historico historial ia largo-plazo corto-plazo movil pasos principal
    principales rapido rapida clasificacion clasificar proforma promedios comparar
    interpretar interpretacion significa necesito necesitas requiere requieren
    disponible disponibles suficiente suficientes mejorar empeorar tendencia tendencias completos
    pagar paga cubre cubrir capacidad empresa empresas pasivo pasivos ratio razon
    quien segundo segunda primero primera lider ranking participacion porcentual
    dias dia vencimiento vencimientos amortizacion depreciacion devengado devengados
    realizado realizados real reales estimacion estimaciones escenario escenarios superavit
    supuesto supuestos inicial final operacion operaciones inversion financiacion
    financiado financiados fuentes fuente completa completo parcial faltante faltantes
    confiable confiables confianza revisar revision trazar trazabilidad relacionar
    combinar juntar separado separadas separado unificar normalizar formatos formato
    nulo nulos vacio vacios repetido repetidos descargar descarga demora lento lenta
    rapido rapido disponible disponible corriente corriente acido acida promedio
    razonabilidad solvencia patrimonio rendimiento rendimientos retorno retornos
    oportunidad presente futuro futuros simple compuesta compuestas capitalizacion patrimonial proyecto
    tasa descuento inflacion estructura composicion tendencia sector sectores
    compromiso compromisos nomina remuneracion remuneraciones compra compras ventas
    politica politicas credito contado proveedores impuestos dividendo dividendos
    operativa operativas actividad actividades cotizado cotizados extraordinario extraordinarios
    mensual mensuales trimestral trimestrales anual anuales dias diario diarios
    proyecte proyectarlo calcularlo calcularlos interpretarlo mejorarlo esto eso esos esas este
    esta estan son fue fueron hay puedo puedes podria deberia sirve sirven ver saber
    dame dime muestra muestran explica explicame ayudame ayuda porque como mas menos
    uno una de del la las un unos unas se me te tu tus su sus nuestro nuestros para con o e
    si no muy tambien realmente juntos juntas cada desde hasta entre todos todas ambos ambas negativo negativa
    limpio limpia original reglas mapeo rol roles clave claves cardinalidad union
    seguridad sheet sheets privacidad soporte persona plan planes monedas coins relacion cobertura
    acid-test kpi kpis clp usd eur ars pen cop mxn gbp iva ebitda tir vp vf
    """.split()
)


# Errores frecuentes observados en conversaciones reales y variantes foneticas.
_TYPO_ALIASES = {
    "analis": "analisis",
    "anlisis": "analisis",
    "balanse": "balance",
    "benefisio": "beneficio",
    "cobransa": "cobranza",
    "cobranzas": "cobranzas",
    "comapara": "compara",
    "comaprar": "comparar",
    "conclucion": "conclusion",
    "convercion": "conversion",
    "cuatno": "cuanto",
    "cuatnos": "cuantos",
    "decsargar": "descargar",
    "desargar": "descargar",
    "dupliados": "duplicados",
    "exel": "excel",
    "endeudamieno": "endeudamiento",
    "estandarisacion": "estandarizacion",
    "estandarizasion": "estandarizacion",
    "finansas": "finanzas",
    "finansiero": "financiero",
    "fitlro": "filtro",
    "fitlros": "filtros",
    "flijo": "flujo",
    "caha": "caja",
    "ganansia": "ganancia",
    "gatsos": "gastos",
    "graifco": "grafico",
    "grafcio": "grafico",
    "ingrezos": "ingresos",
    "ingrseos": "ingresos",
    "interez": "interes",
    "imventario": "inventario",
    "linpieza": "limpieza",
    "liquides": "liquidez",
    "moenda": "moneda",
    "partisipacion": "participacion",
    "pasibo": "pasivo",
    "patrimoio": "patrimonio",
    "peoss": "pesos",
    "perido": "periodo",
    "porcentage": "porcentaje",
    "proyecion": "proyeccion",
    "recomendasion": "recomendacion",
    "recaudasion": "recaudacion",
    "rentavilidad": "rentabilidad",
    "resmuen": "resumen",
    "solbencia": "solvencia",
    "toatl": "total",
    "transasiones": "transacciones",
    "utlidad": "utilidad",
    "vetnas": "ventas",
    "vuena": "buena",
}


# Atajos muy habituales. El segmentador cubre otras combinaciones, mientras estas
# entradas permiten tolerar incluso una pequena errata dentro de una frase pegada.
_JOINED_ALIASES = {
    "analisisfinanciero": "analisis financiero",
    "analisisvertical": "analisis vertical",
    "analisishorizontal": "analisis horizontal",
    "balanceneneral": "balance general",
    "balancegeneral": "balance general",
    "capitaldetrabajo": "capital de trabajo",
    "coberturadeintereses": "cobertura de intereses",
    "costodeoportunidad": "costo de oportunidad",
    "cuantogaste": "cuanto gaste",
    "cuantogano": "cuanto gano",
    "cuantorecaude": "cuanto recaude",
    "cuantosonmisingresos": "cuantos son mis ingresos",
    "cuantossonmisingresos": "cuantos son mis ingresos",
    "cuantossonmisingresostotales": "cuantos son mis ingresos totales",
    "decsargarbasedatos": "descargar base de datos",
    "deficitdecaja": "deficit de caja",
    "depago": "de pago",
    "diasdecobro": "dias de cobro",
    "diasdepago": "dias de pago",
    "estadodecambiosenelpatrimonio": "estado de cambios en el patrimonio",
    "estadodeflujodeefectivo": "estado de flujo de efectivo",
    "estadoderesultados": "estado de resultados",
    "estadosfinancieros": "estados financieros",
    "estadosfinancierosproyectados": "estados financieros proyectados",
    "flujodecaja": "flujo de caja",
    "flujodecajaoperativo": "flujo de caja operativo",
    "gastosoperativos": "gastos operativos",
    "ingresostotales": "ingresos totales",
    "interescompuetso": "interes compuesto",
    "liquidezcorriente": "liquidez corriente",
    "margenbruto": "margen bruto",
    "margenneto": "margen neto",
    "participacionencobranzaporequipo": "participacion en cobranza por equipo",
    "periodocotizado": "periodo cotizado",
    "queporcentajeeseso": "que porcentaje es eso",
    "primerospasos": "primeros pasos",
    "presupuestodecaja": "presupuesto de caja",
    "pruebaacida": "prueba acida",
    "razoncorriente": "razon corriente",
    "rentabilidadsobreactivos": "rentabilidad sobre activos",
    "rentabilidadsobrepatrimonio": "rentabilidad sobre patrimonio",
    "saldofinal": "saldo final",
    "saldoinicial": "saldo inicial",
    "situacionfinanciera": "situacion financiera",
    "valordeldineroeneltiempo": "valor del dinero en el tiempo",
    "valorfuturo": "valor futuro",
    "valorpresente": "valor presente",
    "ventastotales": "ventas totales",
}


_SEGMENT_WORDS = frozenset(word for word in _VOCABULARY if len(word) >= 2)
_MAX_WORD_LENGTH = max(map(len, _SEGMENT_WORDS))


def _edit_distance(left: str, right: str, limit: int) -> int:
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        row_min = i
        for j, char_right in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (char_left != char_right),
                )
            )
            row_min = min(row_min, current[-1])
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


@lru_cache(maxsize=4096)
def _split_joined(token: str) -> tuple[str, ...] | None:
    if len(token) < 8 or token in _VOCABULARY or not token.isalpha():
        return None

    # dp[pos] = (score, parts). Las palabras largas reciben mas peso y se
    # penalizan segmentaciones excesivas para evitar partir nombres propios.
    dp: dict[int, tuple[int, tuple[str, ...]]] = {0: (0, ())}
    for start in range(len(token)):
        if start not in dp:
            continue
        score, parts = dp[start]
        for end in range(start + 2, min(len(token), start + _MAX_WORD_LENGTH) + 1):
            word = token[start:end]
            if word not in _SEGMENT_WORDS:
                continue
            candidate = (score + len(word) ** 2 - 7, parts + (word,))
            if end not in dp or candidate[0] > dp[end][0]:
                dp[end] = candidate
    result = dp.get(len(token))
    if result is None or not 2 <= len(result[1]) <= 8:
        return None
    if max(map(len, result[1])) < 4:
        return None
    return result[1]


@lru_cache(maxsize=4096)
def _correct_known_word(token: str) -> str:
    if token in _TYPO_ALIASES:
        return _TYPO_ALIASES[token]
    if token in _VOCABULARY or token.isdigit() or len(token) < 5:
        return token

    limit = 1 if len(token) <= 6 else 2
    candidates: list[tuple[int, str]] = []
    for word in _VOCABULARY:
        if word[0] != token[0] or abs(len(word) - len(token)) > limit:
            continue
        distance = _edit_distance(token, word, limit)
        if distance <= limit:
            candidates.append((distance, word))
    if not candidates:
        return token
    candidates.sort()
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return token
    return candidates[0][1]


def normalize_query(text: object) -> str:
    """Normaliza una consulta sin modificar identificadores desconocidos."""

    normalized = normalize_basic(text)
    if not normalized:
        return ""
    result: list[str] = []
    for token in normalized.split():
        joined = _JOINED_ALIASES.get(token)
        if joined is None and len(token) >= 10:
            # Tolera una errata en una frase pegada conocida.
            close = [
                key
                for key in _JOINED_ALIASES
                if abs(len(key) - len(token)) <= 2
                and _edit_distance(token, key, 2) <= 2
            ]
            if len(close) == 1:
                joined = _JOINED_ALIASES[close[0]]
        if joined is not None:
            result.extend(joined.split())
            continue
        parts = _split_joined(token)
        if parts is not None:
            result.extend(_correct_known_word(part) for part in parts)
            continue
        result.append(_correct_known_word(token))
    return " ".join(result)
