"""Limpieza dirigida por variables del usuario (Fase 7, POST /clean/assisted).

``interpret_cleaning_instructions`` traduce el texto libre del usuario
("limpia las columnas Fecha y Ventas, no elimines duplicados") a un plan
dirigido determinista: qué columnas incluir/excluir y qué reglas forzar,
SIEMPRE dentro del catálogo acotado de reglas del motor (SPEC §6: nada de
variables infinitas).

Esta es la ÚNICA costura de IA de la interpretación: hoy la implementación es
determinista (matching de nombres de columnas + palabras clave de reglas).
Cuando se active la IA, solo se reemplaza el cuerpo de esta función por una
llamada a Anthropic que devuelva el mismo ``DirectedPlan`` — la interfaz no
cambia y el resto del pipeline no se toca.
"""

from dataclasses import dataclass, field

from .mapping import norm_key, strip_accents_lower

# Sinónimos de roles del negocio → si el usuario dice "las fechas" o "los
# montos", apuntamos a la columna mapeada a ese rol.
_ROLE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "fecha": ("fecha", "fechas"),
    "monto": ("monto", "montos", "venta", "ventas", "ingreso", "ingresos", "importe"),
    "costo": ("costo", "costos", "gasto", "gastos"),
    "cantidad": ("cantidad", "cantidades", "unidades"),
    "cliente": ("cliente", "clientes"),
    "producto": ("producto", "productos", "servicio", "servicios"),
    "categoria": ("categoria", "categorias", "rubro", "rubros"),
    "canal": ("canal", "canales"),
    "sucursal": ("sucursal", "sucursales", "tienda", "tiendas", "local", "locales"),
    "vendedor": ("vendedor", "vendedores", "ejecutivo", "ejecutivos"),
}

# Palabras clave → regla del catálogo (DEFAULT_RULES de clean.py).
_RULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "duplicados": ("duplicado", "duplicados", "repetido", "repetidos", "repetidas"),
    "nulos": ("nulo", "nulos", "vacio", "vacios", "faltante", "faltantes", "sin dato"),
    "fechas": ("fecha invalida", "fechas invalidas", "formato de fecha", "formatos de fecha"),
    "textos": ("texto", "textos", "mayuscula", "mayusculas", "tilde", "tildes", "ortografia"),
    "tipos": ("tipo de dato", "tipos de dato", "tipos de datos", "formato numerico"),
    "columnas_vacias": ("columna vacia", "columnas vacias"),
    "fuera_de_rango": ("outlier", "outliers", "fuera de rango", "atipico", "atipicos", "rango"),
}

_NEGATIONS = ("no ", "sin ", "nunca ", "jamas ", "excepto ", "menos ", "salvo ")
_EXCLUDE_MARKERS = (
    "no toques", "no tocar", "sin tocar", "excluye", "excluir", "ignora",
    "ignorar", "deja fuera", "excepto", "menos la columna", "salvo",
)

MAX_INSTRUCTIONS_CHARS = 2000


@dataclass
class DirectedPlan:
    """Plan de limpieza dirigida: catálogo acotado, nunca variables infinitas."""

    columnas_incluir: list[str] = field(default_factory=list)
    columnas_excluir: list[str] = field(default_factory=list)
    reglas_forzadas: dict[str, bool] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    reconocido: bool = False

    def to_dict(self) -> dict:
        return {
            "columnas_incluir": self.columnas_incluir,
            "columnas_excluir": self.columnas_excluir,
            "reglas_forzadas": self.reglas_forzadas,
            "avisos": self.avisos,
            "reconocido": self.reconocido,
        }


def _clause_is_negated(text_norm: str, position: int) -> bool:
    """¿La mención en `position` está dentro de una cláusula negada/excluyente?

    Mira la ventana de ~40 caracteres previos dentro de la misma cláusula
    (cortada por coma, punto o ' y ')."""
    window_start = max(0, position - 40)
    window = text_norm[window_start:position]
    for cut in (",", ".", ";", " y ", " pero "):
        idx = window.rfind(cut)
        if idx >= 0:
            window = window[idx + len(cut):]
    window = " " + window
    return any(marker in window for marker in _EXCLUDE_MARKERS) or any(
        window.endswith(neg) or f" {neg}" in window for neg in _NEGATIONS
    )


def interpret_cleaning_instructions(
    instructions: str,
    columns: list[str],
    roles: dict[str, str] | None = None,
) -> DirectedPlan:
    """Traduce instrucciones libres a un DirectedPlan determinista.

    # TODO IA: reemplazar el cuerpo por una llamada a Anthropic (backend) que
    # devuelva este mismo DirectedPlan validado contra `columns` y el catálogo
    # de reglas. La firma y el tipo de retorno NO cambian.
    """
    plan = DirectedPlan()
    text = (instructions or "").strip()
    if not text:
        plan.avisos.append("No escribiste instrucciones.")
        return plan
    if len(text) > MAX_INSTRUCTIONS_CHARS:
        text = text[:MAX_INSTRUCTIONS_CHARS]
        plan.avisos.append("Las instrucciones se recortaron a 2.000 caracteres.")

    text_norm = " " + strip_accents_lower(text) + " "
    roles = roles or {}

    # ── 1. Columnas mencionadas por nombre ──
    mentioned: dict[str, int] = {}
    for col in columns:
        key = strip_accents_lower(col)
        if len(norm_key(col)) < 2:
            continue
        pos = text_norm.find(key)
        if pos >= 0:
            mentioned[col] = pos

    # ── 2. Columnas mencionadas por rol del negocio ──
    for role, synonyms in _ROLE_SYNONYMS.items():
        col = roles.get(role)
        if not col or col in mentioned or col not in columns:
            continue
        for word in synonyms:
            pos = text_norm.find(f" {word} ")
            if pos < 0:
                pos = text_norm.find(f" {word},")
            if pos >= 0:
                mentioned[col] = pos + 1
                break

    for col, pos in sorted(mentioned.items(), key=lambda kv: kv[1]):
        if _clause_is_negated(text_norm, pos):
            plan.columnas_excluir.append(col)
        else:
            plan.columnas_incluir.append(col)

    # ── 3. Reglas del catálogo mencionadas ──
    for rule, keywords in _RULE_KEYWORDS.items():
        for word in keywords:
            pos = text_norm.find(word)
            if pos < 0:
                continue
            plan.reglas_forzadas[rule] = not _clause_is_negated(text_norm, pos)
            break

    if plan.reglas_forzadas.get("duplicados"):
        plan.avisos.append(
            "La instrucción de texto solo detecta duplicados. Para eliminarlos debes usar "
            "la acción separada y confirmar explícitamente en la interfaz."
        )

    if "todas las columnas" in text_norm or "todo el archivo" in text_norm:
        plan.columnas_incluir = []
        plan.avisos.append("Se aplicará a todas las columnas (pediste el archivo completo).")
        plan.reconocido = True

    if plan.columnas_incluir:
        plan.avisos.append(
            "Las reglas por columna (fechas, tipos, nulos, outliers) se aplican solo a: "
            + ", ".join(plan.columnas_incluir)
            + ". Duplicados y columnas vacías se evalúan sobre el archivo completo."
        )
    if plan.columnas_excluir:
        plan.avisos.append("Columnas excluidas: " + ", ".join(plan.columnas_excluir) + ".")

    plan.reconocido = bool(
        plan.reconocido or plan.columnas_incluir or plan.columnas_excluir or plan.reglas_forzadas
    )
    if not plan.reconocido:
        plan.avisos.append(
            "No se reconocieron columnas ni reglas del catálogo en tus instrucciones. "
            "Menciona los nombres de las columnas (ej: 'limpia Fecha y Ventas') o reglas "
            "como duplicados, nulos, fechas u outliers."
        )
    return plan
