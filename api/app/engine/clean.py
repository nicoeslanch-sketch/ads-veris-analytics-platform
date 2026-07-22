"""Detección y corrección de problemas del dataset (SPEC §6, POST /clean) — Fase 7.

Detecta: duplicados, valores nulos, fechas inválidas, textos inconsistentes,
tipos de dato incorrectos, columnas vacías y valores fuera de rango.
Con `apply=True` corrige lo que las reglas activas permiten; con `apply=False`
solo reporta (vista previa de "antes de la limpieza").

Cambios profesionales Fase 7 (§5):
- **Nulos numéricos NUNCA se imputan con 0** (§5.1): una venta faltante que se
  vuelve $0 sesga sumas, promedios y márgenes. La regla "nulos" ahora
  normaliza y señaliza (quedan vacíos, contados por columna en el reporte de
  calidad y marcados en la descarga); /metrics los trata como NaN.
- **Outliers IQR solo en columnas métricas** (§5.3): monto, costo y cantidad.
  Nunca sobre IDs, RUT, años ni códigos.
- **Duplicados con criterio explícito y advertencia** (§5.2): la detección es
  por fila completa normalizada; si el archivo no trae una columna
  identificadora (folio/boleta/ID) se advierte que dos ventas legítimamente
  idénticas no se pueden distinguir, en vez de borrar en silencio.
- **Mapeo corregible** (§5.10): `mapping` permite forzar los roles de negocio
  y las reglas por rol lo respetan.
- **Alcance dirigido** (`scope`, Fase 7 §3): las reglas por columna (fechas,
  tipos, nulos, outliers) pueden limitarse a un subconjunto de columnas;
  duplicados y columnas vacías siguen siendo globales.
- **Reporte de calidad por columna** (§5.9): tipo + confianza, rol, nulos,
  corregidos y outliers — la base para que el usuario confíe y para alimentar
  la IA de refinado (costura §5.13).
"""

import copy
import os
import re

import pandas as pd

from .mapping import (
    dedup_norm_key,
    detect_column_roles,
    detect_columns_extended,
    resolve_mapping,
    strip_accents_lower,
)
from .loader import SOURCE_ROWS_ATTR, SOURCE_SHEET_ATTR
from .standardize import (
    is_identifier_column,
    is_semantic_placeholder,
    map_unique,
    parse_date,
    parse_number,
    physical_missing_mask,
    semantic_missing_mask,
    standardize_dataframe,
)

PREVIEW_ROWS = 8

DEFAULT_RULES = {
    "fechas": True,            # Estándar de formato de fecha
    "textos": True,            # Unificar texto
    # Compatibilidad: se acepta y persiste, pero ya no controla detección ni
    # eliminación. Solo `eliminar_duplicados=True` tras confirmación explícita.
    "duplicados": True,
    "tipos": True,             # Convertir tipos de dato
    "nulos": True,             # Normalizar y señalizar valores nulos
    # Fase 12b §9: detectar sí, eliminar NO por defecto — una columna vacía
    # puede ser parte del esquema exigido por otro sistema (misma filosofía
    # conservadora que los duplicados). El usuario la activa si quiere.
    "columnas_vacias": False,
    "fuera_de_rango": True,    # Validar rangos y outliers (solo roles métricos)
}

VALID_ROLES = (
    "fecha", "monto", "costo", "cantidad", "producto", "categoria",
    "cliente", "canal", "sucursal", "vendedor",
)

# Roles métricos: los únicos donde tiene sentido buscar outliers (§5.3) y
# donde imputar 0 sería gravísimo (§5.1).
METRIC_ROLES = {"monto", "costo", "cantidad"}

# Exclusión AMPLIA para análisis estadístico. Esta lista deliberadamente no se
# usa para decidir duplicados: RUT, teléfono, año o código no identifican una
# fila, pero tampoco deben tratarse como métricas sujetas a IQR.
_STATISTICAL_ID_HINT_TOKENS = {
    "id", "folio", "factura", "boleta", "documento", "doc", "nro", "num",
    "numero", "correlativo", "ticket", "orden", "codigo", "cod", "rut",
    "telefono", "fono", "celular", "ano", "year", "postal", "sku", "indice",
    "index", "secuencial", "serie", "dte",
}


def exclude_from_statistical_outliers(column: str, role: str | None = None) -> bool:
    """True si una columna no debe recibir control IQR.

    Es una política independiente de la taxonomía de duplicados. Mantiene la
    protección histórica para IDs, RUT, códigos, teléfonos, años y folios.
    """
    tokens = set(re.sub(r"[^a-z0-9]+", " ", strip_accents_lower(column)).split())
    return bool(tokens & _STATISTICAL_ID_HINT_TOKENS)


_DOCUMENT_ID_TOKENS = {
    "folio", "factura", "boleta", "documento", "doc", "dte", "ticket",
    "orden", "pedido", "guia", "despacho", "envio", "shipment", "delivery",
}
_ENTITY_ID_TOKENS = {"rut", "sku"}
_ATTRIBUTE_ID_TOKENS = {
    "telefono", "fono", "celular", "ano", "year", "postal", "indice",
    "index", "secuencial",
}
_ROW_ID_COMPACT_NAMES = {
    "id", "rowid", "idfila", "filaid", "lineid", "idlinea", "lineaid",
    "transactionid", "idtransaccion", "transaccionid", "idmovimiento",
    "movimientoid", "movimiento",
}


def classify_identifier_kind(column: str, series: pd.Series | None = None) -> str:
    """Clasifica el encabezado para el diagnóstico, nunca para borrar filas.

    Retorna ``fila``, ``documento``, ``entidad`` o ``atributo``. Una detección
    por nombre solo mejora los avisos; la eliminación sigue limitada a filas
    exactas originales y requiere el flag explícito del usuario.
    """
    normalized = strip_accents_lower(column)
    tokens = set(re.sub(r"[^a-z0-9]+", " ", normalized).split())
    compact = re.sub(r"[^a-z0-9]", "", normalized)

    if tokens & _DOCUMENT_ID_TOKENS:
        return "documento"
    if tokens & _ATTRIBUTE_ID_TOKENS:
        return "atributo"
    if tokens & _ENTITY_ID_TOKENS:
        return "entidad"
    if ({"cliente", "producto", "proveedor"} & tokens) and (
        {"id", "codigo", "cod", "numero", "nro", "num"} & tokens
    ):
        return "entidad"
    if compact in _ROW_ID_COMPACT_NAMES:
        return "fila"
    if "id" in tokens and not ({"cliente", "producto", "proveedor"} & tokens):
        return "fila"
    return "atributo"


def _safe_int_env(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _safe_float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return min(maximum, max(minimum, float(os.getenv(name, str(default)))))
    except ValueError:
        return default


DUPLICATE_LARGE_GROUP_THRESHOLD = _safe_int_env(
    "DUPLICATE_LARGE_GROUP_THRESHOLD", 3, 2
)
MAX_AUDIT_DETAILS_IN_RESPONSE = _safe_int_env(
    "MAX_AUDIT_DETAILS_IN_RESPONSE", 5000, 1
)

# Heurística provisional de nulos estructurales. Solo observa categorías
# simples; nunca cambia datos ni combina múltiples variables.
STRUCTURAL_NULL_GROUP_EMPTY_THRESHOLD = _safe_float_env(
    "STRUCTURAL_NULL_GROUP_EMPTY_THRESHOLD", 0.98, 0.5, 1.0
)
STRUCTURAL_NULL_OUTSIDE_FILLED_THRESHOLD = _safe_float_env(
    "STRUCTURAL_NULL_OUTSIDE_FILLED_THRESHOLD", 0.95, 0.5, 1.0
)
STRUCTURAL_NULL_MIN_GROUP_SIZE = _safe_int_env(
    "STRUCTURAL_NULL_MIN_GROUP_SIZE", 20, 2
)
STRUCTURAL_NULL_MAX_GROUP_CARDINALITY = _safe_int_env(
    "STRUCTURAL_NULL_MAX_GROUP_CARDINALITY", 50, 2
)
STRUCTURAL_NULL_MAX_PATTERNS = _safe_int_env(
    "STRUCTURAL_NULL_MAX_PATTERNS", 20, 1
)
_STRUCTURAL_GROUP_ROLES = {None, "producto", "categoria", "canal", "sucursal", "vendedor"}


def _quality(problem_cells: int, total_cells: int) -> float:
    if total_cells <= 0:
        return 0.0
    return round(max(0.0, 1 - problem_cells / total_cells) * 100, 1)


def _analytical_coverage(
    df: pd.DataFrame,
    roles: dict[str, str],
) -> float:
    """Cobertura de valores válidos para seis capacidades analíticas.

    Tener un encabezado con un rol no basta: una columna de ventas llena de
    ``NA`` o fechas ilegibles aporta 0% de cobertura. Para capacidades con
    roles alternativos se usa la alternativa con mayor cobertura real.
    """

    if len(df) == 0:
        return 0.0

    def valid_rate(role: str) -> float:
        column = roles.get(role)
        if not column or column not in df.columns:
            return 0.0
        series = df[column]
        expected_type = (
            "fecha" if role == "fecha" else "numero" if role in {"monto", "costo"} else "texto"
        )
        physical = physical_missing_mask(series)
        semantic = semantic_missing_mask(series, role, column_type=expected_type)
        present = ~(physical | semantic)
        if expected_type == "fecha":
            valid = present & map_unique(series, parse_date).notna()
        elif expected_type == "numero":
            valid = present & map_unique(series, parse_number).notna()
        else:
            valid = present
        return float(valid.sum()) / len(df)

    capabilities = (
        ("fecha",),
        ("monto",),
        ("costo",),
        ("producto", "categoria"),
        ("canal", "sucursal"),
        ("cliente",),
    )
    rates = [max(valid_rate(role) for role in alternatives) for alternatives in capabilities]
    return round(sum(rates) / len(rates) * 100, 1)


def _quality_dimensions(
    df: pd.DataFrame,
    problems: dict,
    roles: dict[str, str],
    identity_inconsistencies: dict,
) -> dict[str, float]:
    rows, columns = len(df), len(df.columns)
    cells = max(rows * max(columns, 1), 1)
    identity_conflicts = (
        identity_inconsistencies["nombre_con_varios_ids"]["conteo"]
        + identity_inconsistencies["id_con_varios_nombres"]["conteo"]
        if identity_inconsistencies
        else 0
    )
    return {
        "completitud": _quality(problems["valores_nulos"], cells),
        "validez": _quality(
            problems["fechas_invalidas"]
            + problems["tipos_incorrectos"]
            + problems["valores_fuera_de_rango"],
            cells,
        ),
        "consistencia": _quality(problems["textos_inconsistentes"], cells),
        "unicidad": _quality(problems["duplicados"] * max(columns, 1), cells),
        "integridad": _quality(identity_conflicts, max(rows, 1)),
        "cobertura_analitica": _analytical_coverage(df, roles),
    }


def _dedup_masks(
    df_original: pd.DataFrame, df_standardized: pd.DataFrame | None = None
) -> tuple[pd.Series, pd.Series]:
    """(exactos originales, normalizados adicionales), categorías excluyentes.

    Los exactos se calculan sobre el DataFrame cargado, antes de estandarizar.
    Los normalizados solo incluyen coincidencias NUEVAS creadas por cambios de
    formato. Ninguna máscara implica por sí sola autorización para eliminar.
    """
    exact = df_original.duplicated(keep="first")
    comparison_source = df_standardized if df_standardized is not None else df_original
    # Fase 11: la clave normalizada se calcula UNA vez por valor único de
    # cada columna (antes era celda por celda: el paso más caro del análisis).
    comparison = pd.DataFrame(
        {
            col: map_unique(comparison_source[col], lambda v: dedup_norm_key(str(v)))
            for col in comparison_source.columns
        },
        index=comparison_source.index,
    )
    normalized = comparison.duplicated(keep="first")
    return exact, normalized & ~exact


def _source_rows(df: pd.DataFrame) -> list[int]:
    rows = list(df.attrs.get(SOURCE_ROWS_ATTR, range(2, len(df) + 2)))
    if len(rows) != len(df):
        return list(range(2, len(df) + 2))
    return [int(row) for row in rows]


def _duplicate_group_stats(df: pd.DataFrame, source_rows: list[int]) -> dict:
    """Estadísticas de grupos exactos sin sumar unidades incompatibles."""
    involved_mask = df.duplicated(keep=False)
    positions = [position for position, involved in enumerate(involved_mask) if involved]
    if not positions:
        return {
            "grupos": 0,
            "filas_involucradas": 0,
            "tamano_maximo_grupo": 0,
            "grupos_contiguos": 0,
            "ejemplos_grupos": [],
        }

    involved = df.iloc[positions]
    grouped_positions: dict[int, list[int]] = {}
    group_ids = involved.groupby(list(df.columns), sort=False, dropna=False).ngroup()
    for position, group_id in zip(positions, group_ids, strict=True):
        grouped_positions.setdefault(int(group_id), []).append(position)

    groups = list(grouped_positions.values())
    examples = [
        {
            "tamano": len(group),
            "filas_origen": [
                source_rows[position]
                for position in group[: min(20, MAX_AUDIT_DETAILS_IN_RESPONSE)]
            ],
            "filas_origen_truncadas": len(group)
            > min(20, MAX_AUDIT_DETAILS_IN_RESPONSE),
        }
        for group in sorted(groups, key=len, reverse=True)[
            : min(5, MAX_AUDIT_DETAILS_IN_RESPONSE)
        ]
    ]
    return {
        "grupos": len(groups),
        "filas_involucradas": len(positions),
        "tamano_maximo_grupo": max(map(len, groups)),
        "grupos_contiguos": sum(
            1 for group in groups if group[-1] - group[0] + 1 == len(group)
        ),
        "ejemplos_grupos": examples,
    }


def _row_identifier_diagnostics(df: pd.DataFrame, source_rows: list[int]) -> tuple[list[dict], int, list[dict]]:
    diagnostics: list[dict] = []
    conflict_examples: list[dict] = []
    total_conflicts = 0

    for col in df.columns:
        if classify_identifier_kind(col, df[col]) != "fila":
            continue
        # Los identificadores son texto: ``None``/``NA`` pueden ser códigos
        # literales. Solo una celda físicamente vacía cuenta como ausente.
        missing = physical_missing_mask(df[col])
        present = df.loc[~missing, col]
        unique_values = int(present.nunique(dropna=False))
        # Fase 18: el nombre no basta — "ID_Sucursal" dentro de una tabla de
        # ventas repite por diseño (clave foránea) y sus repeticiones NO son
        # conflictos. Solo una columna con unicidad alta identifica filas.
        if len(present) and unique_values / len(present) < 0.5:
            continue
        repeated_values = int(present[present.duplicated(keep=False)].nunique(dropna=False))
        conflicts = 0
        if repeated_values:
            repeated_rows = df.loc[~missing & df[col].duplicated(keep=False)]
            for value, group in repeated_rows.groupby(col, sort=False, dropna=False):
                other = group.drop(columns=[col])
                if len(other.drop_duplicates()) <= 1:
                    continue
                conflicts += 1
                if len(conflict_examples) < min(5, MAX_AUDIT_DETAILS_IN_RESPONSE):
                    conflict_examples.append(
                        {
                            "columna": col,
                            "identificador": str(value)[:120],
                            "filas_origen": [source_rows[int(index)] for index in group.index[:10]],
                        }
                    )
        total_conflicts += conflicts
        diagnostics.append(
            {
                "columna": col,
                "completitud_pct": round(len(present) / max(len(df), 1) * 100, 1),
                "proporcion_unicos": round(unique_values / max(len(present), 1), 4),
                "identificadores_repetidos": repeated_values,
                "conflictos_contenido": conflicts,
            }
        )
    return diagnostics, total_conflicts, conflict_examples


def _identity_pairs(
    columns: list[str], roles: dict[str, str], extended: dict
) -> list[tuple[str, str, str]]:
    """(entidad, columna_nombre, columna_id) usando el diccionario extendido."""
    pairs: list[tuple[str, str, str]] = []
    product_name = roles.get("producto")
    client_name = roles.get("cliente")
    for column in columns:
        match = extended.get(column)
        if not match or match.grupo != "identificador":
            continue
        normalized = strip_accents_lower(column)
        if match.rol == "codigo_producto" and product_name:
            pairs.append(("producto", product_name, column))
        elif match.rol == "rut" and client_name:
            pairs.append(("cliente", client_name, column))
        elif match.rol == "id":
            if product_name and any(
                token in normalized for token in ("producto", "sku", "articulo", "item")
            ):
                pairs.append(("producto", product_name, column))
            elif client_name and any(
                token in normalized for token in ("cliente", "customer", "comprador", "rut")
            ):
                pairs.append(("cliente", client_name, column))
    # Evita repetir un par si varias reglas del diccionario convergen.
    return list(dict.fromkeys(pairs))


def _identity_inconsistencies(
    df: pd.DataFrame,
    roles: dict[str, str],
    extended: dict,
    source_rows: list[int],
) -> dict:
    name_conflicts: list[dict] = []
    id_conflicts: list[dict] = []
    analyzed: list[dict] = []

    for entity, name_col, id_col in _identity_pairs(list(df.columns), roles, extended):
        analyzed.append(
            {"entidad": entity, "columna_nombre": name_col, "columna_id": id_col}
        )
        names_to_ids: dict[str, set[str]] = {}
        ids_to_names: dict[str, set[str]] = {}
        name_display: dict[str, str] = {}
        id_display: dict[str, str] = {}
        rows_by_name: dict[str, list[int]] = {}
        rows_by_id: dict[str, list[int]] = {}

        for position, (name, identifier) in enumerate(
            zip(df[name_col].astype(str), df[id_col].astype(str), strict=True)
        ):
            if (
                not name.strip()
                or is_semantic_placeholder(name, entity)
                or not identifier.strip()
            ):
                continue
            name_key = dedup_norm_key(name)
            id_key = dedup_norm_key(identifier)
            if not name_key or not id_key:
                continue
            names_to_ids.setdefault(name_key, set()).add(id_key)
            ids_to_names.setdefault(id_key, set()).add(name_key)
            name_display.setdefault(name_key, name)
            id_display.setdefault(id_key, identifier)
            rows_by_name.setdefault(name_key, []).append(source_rows[position])
            rows_by_id.setdefault(id_key, []).append(source_rows[position])

        for name_key, identifiers in names_to_ids.items():
            if len(identifiers) < 2:
                continue
            name_conflicts.append(
                {
                    "entidad": entity,
                    "columna_nombre": name_col,
                    "columna_id": id_col,
                    "nombre": name_display[name_key],
                    "cantidad_ids": len(identifiers),
                    "ids_ejemplo": [id_display[value] for value in sorted(identifiers)[:5]],
                    "filas_origen": rows_by_name[name_key][:10],
                }
            )
        for id_key, names in ids_to_names.items():
            if len(names) < 2:
                continue
            id_conflicts.append(
                {
                    "entidad": entity,
                    "columna_nombre": name_col,
                    "columna_id": id_col,
                    "id": id_display[id_key],
                    "cantidad_nombres": len(names),
                    "nombres_ejemplo": [name_display[value] for value in sorted(names)[:5]],
                    "filas_origen": rows_by_id[id_key][:10],
                }
            )

    return {
        "nombre_con_varios_ids": {
            "conteo": len(name_conflicts),
            "ejemplos": name_conflicts[:5],
        },
        "id_con_varios_nombres": {
            "conteo": len(id_conflicts),
            "ejemplos": id_conflicts[:5],
        },
        "pares_analizados": analyzed,
    }


def _resolve_mapping(columns: list[str], mapping: dict | None) -> dict[str, str]:
    """Roles del negocio: mapeo automático + correcciones del usuario.
    Fase 11: delega en mapping.resolve_mapping — la MISMA lógica que usa
    /metrics (antes métricas reemplazaba el mapeo completo con el override)."""
    return resolve_mapping(columns, mapping)


def _resolve_scope(columns: list[str], scope: dict | None) -> tuple[set[str], bool]:
    """Columnas donde aplican las reglas por columna. (columnas, es_dirigido).

    Fase 10 §6.3: un alcance dirigido que queda VACÍO (las exclusiones cubren
    todo) significa "no tocar nada" — jamás se reinterpreta como "todas las
    columnas". El endpoint /clean/assisted responde 422 antes de llegar aquí."""
    if not scope:
        return set(columns), False
    include = [c for c in (scope.get("incluir") or []) if c in columns]
    exclude = {c for c in (scope.get("excluir") or []) if c in columns}
    base = set(include) if include else set(columns)
    scoped = base - exclude
    directed = bool(include or exclude)
    if directed:
        return scoped, True
    return set(columns), False


def _column_caches(
    df: pd.DataFrame,
    column_types: dict[str, str],
    roles_by_col: dict[str, str],
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series]]:
    """Máscaras y parseos por columna calculados una sola vez."""
    missing: dict[str, pd.Series] = {}
    physical: dict[str, pd.Series] = {}
    semantic: dict[str, pd.Series] = {}
    dates: dict[str, pd.Series] = {}
    numbers: dict[str, pd.Series] = {}
    for col in df.columns:
        ctype = column_types.get(col, "texto")
        physical[col] = physical_missing_mask(df[col])
        semantic[col] = semantic_missing_mask(
            df[col], roles_by_col.get(col), column_type=ctype
        )
        # La ausencia efectiva depende del contexto. Un token ``NA`` en una
        # categoría textual es literal; en un monto es un placeholder
        # semántico. En ambos casos el texto permanece intacto.
        miss = physical[col] | semantic[col]
        missing[col] = miss
        if ctype == "fecha":
            dates[col] = map_unique(df[col], lambda v: parse_date(v))
        elif ctype == "numero":
            numbers[col] = map_unique(df[col], lambda v: parse_number(v))
    return missing, physical, semantic, dates, numbers


def _structural_null_patterns(
    df: pd.DataFrame,
    physical_cache: dict[str, pd.Series],
    column_types: dict[str, str],
    roles_by_col: dict[str, str],
    source_rows: list[int],
) -> list[dict]:
    """Detecta vacíos probablemente no aplicables según una categoría simple."""
    if len(df) < STRUCTURAL_NULL_MIN_GROUP_SIZE * 2:
        return []
    physical = pd.DataFrame(physical_cache, index=df.index)
    total_empty = physical.sum(axis=0)
    patterns: list[dict] = []

    for group_col in df.columns:
        role = roles_by_col.get(group_col)
        if (
            column_types.get(group_col) != "texto"
            or role not in _STRUCTURAL_GROUP_ROLES
            or is_identifier_column(group_col, df[group_col])
        ):
            continue
        valid_group = ~(
            physical_missing_mask(df[group_col])
            | semantic_missing_mask(
                df[group_col], role, column_type="texto"
            )
        )
        cardinality = int(df.loc[valid_group, group_col].nunique(dropna=False))
        if not 2 <= cardinality <= STRUCTURAL_NULL_MAX_GROUP_CARDINALITY:
            continue

        normalized_group = df[group_col].astype(str).str.strip()
        for group_value, indices in normalized_group[valid_group].groupby(
            normalized_group[valid_group], sort=False
        ).groups.items():
            positions = list(indices)
            group_size = len(positions)
            outside_size = len(df) - group_size
            if group_size < STRUCTURAL_NULL_MIN_GROUP_SIZE or outside_size <= 0:
                continue
            empty_in_group = physical.loc[positions].sum(axis=0)
            group_empty_rate = empty_in_group / group_size
            outside_empty = total_empty - empty_in_group
            outside_filled_rate = 1 - (outside_empty / outside_size)

            for target_col in df.columns:
                if target_col == group_col:
                    continue
                empty_rate = float(group_empty_rate[target_col])
                filled_rate = float(outside_filled_rate[target_col])
                if (
                    empty_rate < STRUCTURAL_NULL_GROUP_EMPTY_THRESHOLD
                    or filled_rate < STRUCTURAL_NULL_OUTSIDE_FILLED_THRESHOLD
                ):
                    continue
                empty_positions = [
                    int(index)
                    for index in positions
                    if bool(physical_cache[target_col].loc[index])
                ]
                patterns.append(
                    {
                        "columna": target_col,
                        "agrupado_por": group_col,
                        "grupo": str(group_value)[:160],
                        "filas_grupo": group_size,
                        "vacio_en_grupo_pct": round(empty_rate * 100, 1),
                        "informado_fuera_pct": round(filled_rate * 100, 1),
                        "filas_origen_ejemplo": [
                            source_rows[position] for position in empty_positions[:5]
                        ],
                        "mensaje": (
                            f"Posible patrón estructural: la columna {target_col} está vacía "
                            f"en {round(empty_rate * 100, 1)}% de las filas de "
                            f"{group_col}={group_value}, pero informada en "
                            f"{round(filled_rate * 100, 1)}% fuera; puede representar "
                            "un campo no aplicable."
                        ),
                    }
                )

    patterns.sort(
        key=lambda item: (
            item["filas_grupo"], item["vacio_en_grupo_pct"], item["informado_fuera_pct"]
        ),
        reverse=True,
    )
    return patterns[:STRUCTURAL_NULL_MAX_PATTERNS]


def _detect_problems(
    df: pd.DataFrame,
    column_types: dict[str, str],
    text_changes: int,
    roles_by_col: dict[str, str],
    scoped_cols: set[str],
    exact_duplicate_mask: pd.Series | None = None,
    normalized_only_mask: pd.Series | None = None,
    source_rows: list[int] | None = None,
    include_structural_patterns: bool = True,
) -> dict:
    miss_cache, physical_cache, semantic_cache, date_cache, num_cache = _column_caches(
        df, column_types, roles_by_col
    )
    # Solo una columna físicamente vacía puede eliminarse automáticamente.
    # Una columna llena de tokens literales nunca se borra en silencio.
    empty_columns = [col for col in df.columns if bool(physical_cache[col].all())]
    if exact_duplicate_mask is None or normalized_only_mask is None:
        exact_duplicate_mask, normalized_only_mask = _dedup_masks(df, df)

    physical_nulls = 0
    semantic_nulls = 0
    invalid_dates = 0
    wrong_types = 0
    out_of_range = 0
    zero_amounts = 0
    negative_amounts = 0
    per_column: dict[str, dict] = {}

    for col in df.columns:
        info: dict = {
            "rol": roles_by_col.get(col),
            "tipo": column_types.get(col, "texto"),
            "en_alcance": col in scoped_cols,
        }
        miss = miss_cache[col]
        col_physical = int(physical_cache[col].sum())
        col_semantic = int(semantic_cache[col].sum())
        physical_nulls += col_physical
        semantic_nulls += col_semantic
        info["nulos"] = col_physical
        info["nulos_fisicos"] = col_physical
        info["nulos_semanticos"] = col_semantic
        info["nulos_pct"] = round(col_physical / max(len(df), 1) * 100, 1)
        if col in empty_columns:
            info["vacia"] = True
            per_column[col] = info
            continue
        ctype = column_types.get(col, "texto")
        if ctype == "fecha":
            invalid_mask = ~miss & date_cache[col].isna()
            invalid = int(invalid_mask.sum())
            invalid_dates += invalid
            info["fechas_invalidas"] = invalid
            if invalid:
                # Muestras para el refinado IA (§5.13): qué valores no se pudieron reparar.
                info["ejemplos_invalidos"] = [str(v) for v in df[col][invalid_mask].head(3)]
        elif ctype == "numero":
            parsed = num_cache[col]
            wrong_mask = ~miss & parsed.isna()
            wrong = int(wrong_mask.sum())
            wrong_types += wrong
            info["tipos_incorrectos"] = wrong
            if wrong:
                info["ejemplos_invalidos"] = [str(v) for v in df[col][wrong_mask].head(3)]
            # Outliers SOLO en roles métricos (§5.3): jamás IDs, RUT o años.
            role = roles_by_col.get(col)
            if role == "monto":
                col_zero = int(parsed.eq(0).sum())
                col_negative = int(parsed.lt(0).sum())
                zero_amounts += col_zero
                negative_amounts += col_negative
                info["montos_cero"] = col_zero
                info["montos_negativos"] = col_negative
            if role in METRIC_ROLES and not exclude_from_statistical_outliers(col, role):
                numbers = parsed.dropna()
                if len(numbers) >= 8:
                    q1, q3 = numbers.quantile(0.25), numbers.quantile(0.75)
                    iqr = q3 - q1
                    if iqr > 0:
                        lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
                        below = int((numbers < lower).sum())
                        above = int((numbers > upper).sum())
                        col_outliers = below + above
                        out_of_range += col_outliers
                        info["outliers"] = col_outliers
                        info["outliers_iqr"] = {
                            "q1": round(float(q1), 4),
                            "q3": round(float(q3), 4),
                            "iqr": round(float(iqr), 4),
                            "limite_inferior": round(float(lower), 4),
                            "limite_superior": round(float(upper), 4),
                            "bajo_limite": below,
                            "sobre_limite": above,
                            "total": col_outliers,
                        }
        per_column[col] = info

    origin_rows = source_rows or list(range(2, len(df) + 2))
    structural_patterns = (
        _structural_null_patterns(
            df, physical_cache, column_types, roles_by_col, origin_rows
        )
        if include_structural_patterns
        else []
    )
    for pattern in structural_patterns:
        column_info = per_column.get(pattern["columna"])
        if column_info is not None:
            column_info["posibles_nulos_estructurales"] = (
                column_info.get("posibles_nulos_estructurales", 0) + 1
            )

    return {
        # Semántica estable: exactos del archivo original vs coincidencias
        # adicionales tras normalización. Nunca dependen del nombre de un ID.
        "duplicados": int(exact_duplicate_mask.sum()),
        "duplicados_probables": int(normalized_only_mask.sum()),
        # Alias histórico corregido: ahora representa exclusivamente celdas
        # físicamente vacías, no placeholders semánticos.
        "valores_nulos": physical_nulls,
        "nulos_fisicos": physical_nulls,
        "nulos_semanticos": semantic_nulls,
        "posibles_nulos_estructurales": len(structural_patterns),
        "fechas_invalidas": invalid_dates,
        "textos_inconsistentes": text_changes,
        "tipos_incorrectos": wrong_types,
        "columnas_vacias": len(empty_columns),
        "montos_cero": zero_amounts,
        "montos_negativos": negative_amounts,
        "outliers_iqr": out_of_range,
        # Alias compatible con versiones anteriores del frontend.
        "valores_fuera_de_rango": out_of_range,
        "_columnas_vacias_nombres": empty_columns,
        "_duplicados_mask": exact_duplicate_mask,
        "_duplicados_normalizados_mask": normalized_only_mask,
        "_por_columna": per_column,
        "_patrones_estructurales": structural_patterns,
        "_caches": (
            miss_cache, physical_cache, semantic_cache, date_cache, num_cache
        ),
    }


def _preview_with_issues(
    df: pd.DataFrame,
    column_types: dict[str, str],
    duplicated_mask: pd.Series,
    caches: tuple[dict, dict, dict],
    source_rows: list[int],
) -> dict:
    """Primeras filas + coordenadas de celdas problemáticas para resaltarlas."""
    preview = df.head(PREVIEW_ROWS)
    miss_cache, _physical_cache, semantic_cache, date_cache, num_cache = caches
    issues: list[dict] = []
    for row_index in range(len(preview)):
        fila_origen = source_rows[row_index]
        if bool(duplicated_mask.iloc[row_index]):
            issues.append(
                {
                    "fila": row_index,
                    "fila_origen": fila_origen,
                    "columna": "*",
                    "tipo": "duplicado",
                }
            )
        for col in preview.columns:
            if bool(semantic_cache[col].iloc[row_index]):
                issues.append(
                    {
                        "fila": row_index,
                        "fila_origen": fila_origen,
                        "columna": col,
                        "tipo": "nulo_semantico",
                    }
                )
                continue
            if bool(miss_cache[col].iloc[row_index]):
                issues.append(
                    {
                        "fila": row_index,
                        "fila_origen": fila_origen,
                        "columna": col,
                        "tipo": "nulo",
                    }
                )
                continue
            ctype = column_types.get(col, "texto")
            if ctype == "fecha" and pd.isna(date_cache[col].iloc[row_index]):
                issues.append(
                    {
                        "fila": row_index,
                        "fila_origen": fila_origen,
                        "columna": col,
                        "tipo": "fecha_invalida",
                    }
                )
            elif ctype == "numero" and pd.isna(num_cache[col].iloc[row_index]):
                issues.append(
                    {
                        "fila": row_index,
                        "fila_origen": fila_origen,
                        "columna": col,
                        "tipo": "tipo_incorrecto",
                    }
                )
    return {
        "columnas": list(preview.columns),
        "filas": [[str(v) for v in row] for row in preview.itertuples(index=False, name=None)],
        "issues": issues,
    }


def analyze_and_clean(
    df_original: pd.DataFrame,
    rules: dict | None,
    apply: bool,
    mapping: dict | None = None,
    scope: dict | None = None,
    eliminar_duplicados: bool = False,
    standardized: tuple[pd.DataFrame, dict] | None = None,
) -> dict:
    active = {**DEFAULT_RULES, **(rules or {})}

    # Conservamos la identidad cargada ANTES de estandarizar. Dos filas que se
    # vuelven iguales por mayúsculas, espacios o formato son solo candidatas a
    # revisión y jamás entran en la máscara eliminable.
    if standardized is None:
        df, std_report = standardize_dataframe(df_original, mapping=mapping)
    else:
        # El caché comparte un resultado inmutable entre endpoints. Cada run
        # recibe copias para que drop/asignaciones nunca contaminen otra sesión.
        df = standardized[0].copy(deep=True)
        df.attrs = copy.deepcopy(standardized[0].attrs)
        std_report = copy.deepcopy(standardized[1])
    loaded_original = df_original.copy()
    loaded_original.columns = df.columns
    source_rows = _source_rows(df_original)
    source_sheet = df_original.attrs.get(SOURCE_SHEET_ATTR)
    exact_original_mask, normalized_only_mask = _dedup_masks(loaded_original, df)

    column_types = std_report["column_types"]
    text_changes = std_report["cambios"]["textos_normalizados"]

    roles = _resolve_mapping(list(df.columns), mapping)
    roles_by_col = {col: role for role, col in roles.items()}
    scoped_cols, directed = _resolve_scope(list(df.columns), scope)

    rows_before, cols_before = len(df), len(df.columns)
    total_cells = rows_before * cols_before
    df_before_clean = df.copy(deep=False)

    problems = _detect_problems(
        df,
        column_types,
        text_changes,
        roles_by_col,
        scoped_cols,
        exact_original_mask,
        normalized_only_mask,
        source_rows,
    )
    empty_columns: list[str] = problems.pop("_columnas_vacias_nombres")
    duplicated_mask: pd.Series = problems.pop("_duplicados_mask")
    problems.pop("_duplicados_normalizados_mask")
    per_column: dict = problems.pop("_por_columna")
    structural_patterns: list[dict] = problems.pop("_patrones_estructurales")
    caches = problems.pop("_caches")

    preview = _preview_with_issues(df, column_types, duplicated_mask, caches, source_rows)

    group_stats = _duplicate_group_stats(loaded_original, source_rows)
    # Los conflictos se evalúan sobre la versión estandarizada. Diferencias
    # puramente visuales son duplicados normalizados, no movimientos distintos.
    row_ids, conflicts_id, conflict_examples = _row_identifier_diagnostics(df, source_rows)
    possible_omitted_granularity = bool(
        not row_ids
        and group_stats["tamano_maximo_grupo"] >= DUPLICATE_LARGE_GROUP_THRESHOLD
    )
    duplicate_detail = {
        "exactos": problems["duplicados"],
        "normalizados": problems["duplicados_probables"],
        "conflictos_id": conflicts_id,
        **group_stats,
        "identificadores_fila": row_ids,
        "ejemplos_conflictos_id": conflict_examples,
        "posible_granularidad_omitida": possible_omitted_granularity,
        "eliminacion_habilitada": bool(eliminar_duplicados),
        "filas_seleccionadas_para_eliminar": (
            problems["duplicados"] if eliminar_duplicados else 0
        ),
        "filas_eliminadas": 0,
    }
    detected_duplicate_rows = [
        {
            "fila_origen": int(source_rows[position]),
            "hoja_origen": source_sheet,
            "regla": "duplicado_exacto_original",
            "categoria": "duplicado_detectado",
            "aplicada": False,
            "confianza": 1.0,
            "motivo": "Coincide exactamente con una fila anterior del archivo original.",
        }
        for position, duplicated in enumerate(duplicated_mask)
        if bool(duplicated)
    ]

    # Enriquecer el reporte de calidad con lo que sabe la estandarización
    # y el mapeo universal (Fase 9): rol extendido + método y confianza.
    extended = detect_columns_extended(list(df.columns))
    identity_inconsistencies = _identity_inconsistencies(
        df, roles, extended, source_rows
    )
    for col, info in per_column.items():
        match = extended.get(col)
        if match:
            info["rol_extendido"] = match.rol
            info["grupo_rol"] = match.grupo
            info["match_diccionario"] = {
                "palabra_clave": match.palabra_clave,
                "metodo": match.metodo,
                "confianza": match.confianza,
            }
        info["confianza_tipo"] = std_report["column_confidence"].get(col)
        convention = std_report["convenciones_numericas"].get(col)
        if convention:
            info["convencion_numerica"] = convention
        if info.get("rol") in METRIC_ROLES:
            info["politica_nulos"] = "preservados (nunca se imputa 0 en montos)"

    # Los avisos de la estandarización (fechas mixtas, comas ambiguas,
    # mojibake) también le llegan a quien solo mira la limpieza.
    avisos: list[str] = list(std_report.get("avisos", []))
    duplicados_criterio = "fila_exacta_original_con_confirmacion"
    if problems["duplicados"] > 0:
        avisos.append(
            f"Se detectaron {problems['duplicados']} repetición(es) exacta(s) en el "
            "archivo original. Se conservarán mientras no confirmes explícitamente "
            "su eliminación."
        )
    if possible_omitted_granularity:
        avisos.append(
            "Se detectaron grupos de hasta "
            f"{group_stats['tamano_maximo_grupo']} filas idénticas y el archivo no contiene "
            "un identificador único por registro. Esto puede indicar que el extracto "
            "omitió una variable diferenciadora —por ejemplo, persona, línea, movimiento o "
            "documento— o que el proceso de extracción multiplicó registros. Verifica el "
            "origen antes de eliminar."
        )
    if problems.get("duplicados_probables", 0) > 0:
        avisos.append(
            f"{problems['duplicados_probables']} coincidencia(s) adicional(es) aparecieron "
            "solo después de normalizar mayúsculas o formato. Se informan para revisión y "
            "no se eliminarán, incluso si confirmas los duplicados exactos."
        )
    if conflicts_id:
        avisos.append(
            f"Se detectaron {conflicts_id} identificador(es) de fila repetido(s) con "
            "contenido distinto. Son conflictos de origen, no duplicados eliminables."
        )
    for example in identity_inconsistencies["nombre_con_varios_ids"]["ejemplos"][:2]:
        avisos.append(
            f"El {example['entidad']} '{example['nombre']}' aparece con "
            f"{example['cantidad_ids']} códigos distintos; puede ser un error de "
            "digitación o entidades efectivamente distintas — revísalo en el origen."
        )
    for example in identity_inconsistencies["id_con_varios_nombres"]["ejemplos"][:2]:
        avisos.append(
            f"El código '{example['id']}' aparece con {example['cantidad_nombres']} "
            f"nombres de {example['entidad']} distintos; se conserva sin fusionar."
        )
    if problems["nulos_semanticos"]:
        avisos.append(
            f"Se detectaron {problems['nulos_semanticos']} placeholder(s) dependientes "
            "del rol. Se conservaron literalmente y se señalan como nulos semánticos, "
            "separados de las celdas físicamente vacías."
        )
    avisos.extend(pattern["mensaje"] for pattern in structural_patterns)
    fusiones = std_report.get("fusiones_texto", {})
    if fusiones.get("total"):
        ejemplos = ", ".join(f"{a} → {b}" for a, b in fusiones.get("ejemplos", [])[:3])
        avisos.append(
            f"Se unificaron {fusiones['total']} texto(s) con errores de tipeo "
            f"(fuzzy matching). Ejemplos: {ejemplos}."
        )
    if directed:
        fuera = [c for c in df.columns if c not in scoped_cols]
        if fuera:
            avisos.append(
                "Limpieza dirigida: las reglas por columna no se aplicaron a: "
                + ", ".join(fuera) + "."
            )

    problem_cells = (
        problems["valores_nulos"]
        + problems["fechas_invalidas"]
        + problems["tipos_incorrectos"]
        + problems["duplicados"] * cols_before
    )
    quality_before = _quality(problem_cells, total_cells)

    scoped_nulls = sum(
        per_column[c].get("nulos", 0) for c in scoped_cols if c in per_column
    )
    corrections = {
        # `rules.duplicados` queda deprecada: detectar es obligatorio y borrar
        # depende exclusivamente de esta decisión separada y explícita.
        "filas_duplicadas_a_eliminar": (
            problems["duplicados"] if eliminar_duplicados else 0
        ),
        "filas_duplicadas_eliminadas": 0,
        # §5.1: los nulos ya NO se reemplazan por 0 — se normalizan y señalizan.
        "valores_nulos_normalizados": scoped_nulls if active["nulos"] else 0,
        "fechas_a_estandarizar": std_report["cambios"]["fechas_estandarizadas"]
        + (problems["fechas_invalidas"] if active["fechas"] else 0),
        "textos_a_unificar": text_changes if active["textos"] else 0,
        "tipos_a_corregir": problems["tipos_incorrectos"] if active["tipos"] else 0,
        "columnas_vacias_a_eliminar": problems["columnas_vacias"] if active["columnas_vacias"] else 0,
        "valores_fuera_de_rango_a_revisar": problems["valores_fuera_de_rango"] if active["fuera_de_rango"] else 0,
    }

    quality_after = quality_before
    rows_after, cols_after = rows_before, cols_before
    clean_source_rows = list(source_rows)
    removed_duplicate_rows: list[dict] = []
    remaining_exact_mask = exact_original_mask.reset_index(drop=True)
    remaining_normalized_mask = normalized_only_mask.reset_index(drop=True)

    if apply:
        miss_cache, _physical_cache, _semantic_cache, date_cache, num_cache = caches
        if active["columnas_vacias"] and empty_columns:
            df = df.drop(columns=empty_columns)
        if eliminar_duplicados:
            removed_positions = [
                position for position, duplicated in enumerate(duplicated_mask) if duplicated
            ]
            # Este detalle es privado (se excluye de la respuesta HTTP) y debe
            # quedar completo para la hoja Observaciones de la descarga.
            for position in removed_positions:
                removed_duplicate_rows.append(
                    {
                        "fila_origen": source_rows[position],
                        "hoja_origen": source_sheet,
                        "regla": "duplicado_exacto_original",
                        "categoria": "fila_eliminada",
                        "aplicada": True,
                        "confianza": 1.0,
                        "motivo": "Eliminación confirmada explícitamente por el usuario.",
                    }
                )
            keep = ~duplicated_mask
            clean_source_rows = [
                source_rows[position] for position, should_keep in enumerate(keep) if should_keep
            ]
            remaining_exact_mask = exact_original_mask.loc[keep].reset_index(drop=True)
            remaining_normalized_mask = normalized_only_mask.loc[keep].reset_index(drop=True)
            df = df.loc[keep].reset_index(drop=True)
            corrections["filas_duplicadas_eliminadas"] = len(removed_positions)
            duplicate_detail["filas_eliminadas"] = len(removed_positions)

        # Fase 12b (P0): las fechas y números NO interpretables se CONSERVAN.
        # Antes se reemplazaban por "" — se destruía el valor original
        # ("$ 15.O00", "31/02/2026", "Pendiente confirmar") y la descarga ya no
        # permitía reconstruirlo, contradiciendo la promesa de datos intactos.
        # Ahora: se conservan tal cual, quedan marcados en la descarga como
        # no interpretables, los indicadores los ignoran al calcular (parse →
        # None) y siguen contando como problema en la calidad post-limpieza —
        # la calidad ya no puede "mejorar" borrando la evidencia.
        # §5.1: sin imputación de nulos — nunca "0" en montos/costos/cantidades.

        rows_after, cols_after = len(df), len(df.columns)
        df.attrs[SOURCE_ROWS_ATTR] = clean_source_rows
        df.attrs[SOURCE_SHEET_ATTR] = source_sheet
        remaining = _detect_problems(
            df,
            column_types,
            text_changes=0,
            roles_by_col=roles_by_col,
            scoped_cols=scoped_cols,
            exact_duplicate_mask=remaining_exact_mask,
            normalized_only_mask=remaining_normalized_mask,
            source_rows=clean_source_rows,
            # Ya fueron auditados antes de aplicar. Esta segunda pasada solo
            # calcula calidad residual y no debe repetir el análisis grupal.
            include_structural_patterns=False,
        )
        remaining.pop("_columnas_vacias_nombres")
        remaining.pop("_duplicados_mask")
        remaining.pop("_duplicados_normalizados_mask")
        remaining.pop("_por_columna")
        remaining.pop("_patrones_estructurales")
        remaining.pop("_caches")
        # Fase 13 (P0.1): la calidad DESPUÉS usa la MISMA base que la calidad
        # ANTES (nulos + fechas + tipos + duplicados). Antes excluía los nulos
        # preservados y una base con 10.000 celdas vacías podía "subir a 100%"
        # sin que se corrigiera nada — una mejora falsa.
        remaining_cells = (
            remaining["valores_nulos"]
            + remaining["fechas_invalidas"]
            + remaining["tipos_incorrectos"]
            + remaining["duplicados"] * max(cols_after, 1)
        )
        quality_after = _quality(remaining_cells, rows_after * max(cols_after, 1))

    calidad_dimensiones_antes = _quality_dimensions(
        df_before_clean, problems, roles, identity_inconsistencies
    )
    if apply:
        identidad_despues = _identity_inconsistencies(
            df, roles, extended, clean_source_rows
        )
        calidad_dimensiones_despues = _quality_dimensions(
            df, remaining, roles, identidad_despues
        )
    else:
        calidad_dimensiones_despues = dict(calidad_dimensiones_antes)

    return {
        "resumen": {
            "filas_antes": rows_before,
            "filas_despues": rows_after,
            "columnas_antes": cols_before,
            "columnas_despues": cols_after,
            "calidad_antes": quality_before,
            "calidad_despues": quality_after,
            # Alias histórico: representaba el estado inicial. Se mantiene
            # para clientes Fase 15 y se agregan las dos etapas explícitas.
            "calidad_dimensiones": calidad_dimensiones_antes,
            "calidad_dimensiones_antes": calidad_dimensiones_antes,
            "calidad_dimensiones_despues": calidad_dimensiones_despues,
            "aplicado": apply,
        },
        "problemas": problems,
        "correcciones": corrections,
        "reglas_activas": active,
        "opciones_aplicacion": {"eliminar_duplicados": bool(eliminar_duplicados)},
        "duplicados_detalle": duplicate_detail,
        "nulos_detalle": {
            "fisicos": problems["nulos_fisicos"],
            "semanticos": problems["nulos_semanticos"],
            "posibles_estructurales": structural_patterns,
        },
        "inconsistencias_identidad": identity_inconsistencies,
        "preview": preview,
        "estandarizacion": std_report["cambios"],
        "column_types": column_types,
        "mapeo": roles,
        "reporte_calidad": per_column,
        "avisos": avisos,
        "duplicados_criterio": duplicados_criterio,
        "fusiones_texto": fusiones,
        "mojibake_auditoria": std_report.get("mojibake_auditoria", []),
        "_ambiguedades_numericas": std_report.get("ambiguedades_numericas", {}),
        "_df_limpio": df if apply else None,
        "_source_rows_limpio": clean_source_rows if apply else source_rows,
        "_filas_duplicadas_eliminadas": removed_duplicate_rows,
        "_filas_duplicadas_detectadas": detected_duplicate_rows,
    }
