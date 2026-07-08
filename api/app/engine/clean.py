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

import re

import pandas as pd

from .mapping import dedup_norm_key, detect_column_roles, strip_accents_lower
from .standardize import (
    is_missing,
    missing_mask,
    parse_date,
    parse_number,
    standardize_dataframe,
)

PREVIEW_ROWS = 8

DEFAULT_RULES = {
    "fechas": True,            # Estándar de formato de fecha
    "textos": True,            # Unificar texto
    "duplicados": True,        # Eliminar duplicados
    "tipos": True,             # Convertir tipos de dato
    "nulos": True,             # Normalizar y señalizar valores nulos
    "columnas_vacias": True,   # Eliminar columnas vacías
    "fuera_de_rango": True,    # Validar rangos y outliers (solo roles métricos)
}

VALID_ROLES = (
    "fecha", "monto", "costo", "cantidad", "producto", "categoria",
    "cliente", "canal", "sucursal", "vendedor",
)

# Roles métricos: los únicos donde tiene sentido buscar outliers (§5.3) y
# donde imputar 0 sería gravísimo (§5.1).
METRIC_ROLES = {"monto", "costo", "cantidad"}

_ID_HINT_TOKENS = {
    "id", "folio", "factura", "boleta", "documento", "doc", "nro", "num",
    "numero", "correlativo", "ticket", "orden", "codigo", "cod", "rut",
    "telefono", "fono", "ano", "year", "postal",
}


def _is_id_like(column: str) -> bool:
    tokens = set(re.sub(r"[^a-z0-9]+", " ", strip_accents_lower(column)).split())
    return bool(tokens & _ID_HINT_TOKENS)


def _quality(problem_cells: int, total_cells: int) -> float:
    if total_cells <= 0:
        return 0.0
    return round(max(0.0, 1 - problem_cells / total_cells) * 100, 1)


def _dedup_mask(df: pd.DataFrame) -> pd.Series:
    """Máscara de filas duplicadas usando comparación normalizada (sin mayúsculas ni puntuación).
    Detecta duplicados aunque difieran en formato: '76.123.456-7' == '76123456-7',
    'Santiago Centro' == 'SANTIAGO CENTRO', etc."""
    comparison = df.map(lambda v: dedup_norm_key(str(v)))
    return comparison.duplicated(keep="first")


def _resolve_mapping(columns: list[str], mapping: dict | None) -> dict[str, str]:
    """Roles del negocio: usa el mapeo corregido por el usuario si es válido."""
    detected = detect_column_roles(columns)
    if not mapping:
        return detected
    resolved = dict(detected)
    for role, col in mapping.items():
        role_key = str(role).strip().lower()
        if role_key not in VALID_ROLES:
            continue
        if not col:
            resolved.pop(role_key, None)
            continue
        if col in columns:
            # Un mismo nombre de columna no puede cumplir dos roles.
            for other_role, other_col in list(resolved.items()):
                if other_col == col and other_role != role_key:
                    resolved.pop(other_role)
            resolved[role_key] = col
    return resolved


def _resolve_scope(columns: list[str], scope: dict | None) -> tuple[set[str], bool]:
    """Columnas donde aplican las reglas por columna. (columnas, es_dirigido)."""
    if not scope:
        return set(columns), False
    include = [c for c in (scope.get("incluir") or []) if c in columns]
    exclude = {c for c in (scope.get("excluir") or []) if c in columns}
    base = set(include) if include else set(columns)
    scoped = base - exclude
    directed = bool(include or exclude)
    return (scoped or set(columns)), directed


def _column_caches(
    df: pd.DataFrame, column_types: dict[str, str]
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series]]:
    """Parseos por columna calculados UNA vez (§5.8): missing, fechas y números."""
    missing: dict[str, pd.Series] = {}
    dates: dict[str, pd.Series] = {}
    numbers: dict[str, pd.Series] = {}
    for col in df.columns:
        miss = missing_mask(df[col])
        missing[col] = miss
        ctype = column_types.get(col, "texto")
        if ctype == "fecha":
            dates[col] = df[col].map(lambda v: parse_date(v))
        elif ctype == "numero":
            numbers[col] = df[col].map(lambda v: parse_number(v))
    return missing, dates, numbers


def _detect_problems(
    df: pd.DataFrame,
    column_types: dict[str, str],
    text_changes: int,
    roles_by_col: dict[str, str],
    scoped_cols: set[str],
) -> dict:
    miss_cache, date_cache, num_cache = _column_caches(df, column_types)
    empty_columns = [col for col in df.columns if bool(miss_cache[col].all())]
    duplicated_mask = _dedup_mask(df)

    nulls = 0
    invalid_dates = 0
    wrong_types = 0
    out_of_range = 0
    per_column: dict[str, dict] = {}

    for col in df.columns:
        info: dict = {
            "rol": roles_by_col.get(col),
            "tipo": column_types.get(col, "texto"),
            "en_alcance": col in scoped_cols,
        }
        if col in empty_columns:
            info["vacia"] = True
            per_column[col] = info
            continue
        miss = miss_cache[col]
        col_nulls = int(miss.sum())
        nulls += col_nulls
        info["nulos"] = col_nulls
        info["nulos_pct"] = round(col_nulls / max(len(df), 1) * 100, 1)
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
            if role in METRIC_ROLES and not _is_id_like(col):
                numbers = parsed.dropna()
                if len(numbers) >= 8:
                    q1, q3 = numbers.quantile(0.25), numbers.quantile(0.75)
                    iqr = q3 - q1
                    if iqr > 0:
                        lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
                        col_outliers = int(((numbers < lower) | (numbers > upper)).sum())
                        out_of_range += col_outliers
                        info["outliers"] = col_outliers
        per_column[col] = info

    return {
        "duplicados": int(duplicated_mask.sum()),
        "valores_nulos": nulls,
        "fechas_invalidas": invalid_dates,
        "textos_inconsistentes": text_changes,
        "tipos_incorrectos": wrong_types,
        "columnas_vacias": len(empty_columns),
        "valores_fuera_de_rango": out_of_range,
        "_columnas_vacias_nombres": empty_columns,
        "_duplicados_mask": duplicated_mask,
        "_por_columna": per_column,
        "_caches": (miss_cache, date_cache, num_cache),
    }


def _preview_with_issues(
    df: pd.DataFrame,
    column_types: dict[str, str],
    duplicated_mask: pd.Series,
    caches: tuple[dict, dict, dict],
) -> dict:
    """Primeras filas + coordenadas de celdas problemáticas para resaltarlas."""
    preview = df.head(PREVIEW_ROWS)
    miss_cache, date_cache, num_cache = caches
    issues: list[dict] = []
    for row_index in range(len(preview)):
        if bool(duplicated_mask.iloc[row_index]):
            issues.append({"fila": row_index, "columna": "*", "tipo": "duplicado"})
        for col in preview.columns:
            if bool(miss_cache[col].iloc[row_index]):
                issues.append({"fila": row_index, "columna": col, "tipo": "nulo"})
                continue
            ctype = column_types.get(col, "texto")
            if ctype == "fecha" and pd.isna(date_cache[col].iloc[row_index]):
                issues.append({"fila": row_index, "columna": col, "tipo": "fecha_invalida"})
            elif ctype == "numero" and pd.isna(num_cache[col].iloc[row_index]):
                issues.append({"fila": row_index, "columna": col, "tipo": "tipo_incorrecto"})
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
) -> dict:
    active = {**DEFAULT_RULES, **(rules or {})}

    # La limpieza siempre parte de datos estandarizados (idempotente).
    df, std_report = standardize_dataframe(df_original)
    column_types = std_report["column_types"]
    text_changes = std_report["cambios"]["textos_normalizados"]

    roles = _resolve_mapping(list(df.columns), mapping)
    roles_by_col = {col: role for role, col in roles.items()}
    scoped_cols, directed = _resolve_scope(list(df.columns), scope)

    rows_before, cols_before = len(df), len(df.columns)
    total_cells = rows_before * cols_before

    problems = _detect_problems(df, column_types, text_changes, roles_by_col, scoped_cols)
    empty_columns: list[str] = problems.pop("_columnas_vacias_nombres")
    duplicated_mask: pd.Series = problems.pop("_duplicados_mask")
    per_column: dict = problems.pop("_por_columna")
    caches = problems.pop("_caches")

    preview = _preview_with_issues(df, column_types, duplicated_mask, caches)

    # Enriquecer el reporte de calidad con lo que sabe la estandarización.
    for col, info in per_column.items():
        info["confianza_tipo"] = std_report["column_confidence"].get(col)
        convention = std_report["convenciones_numericas"].get(col)
        if convention:
            info["convencion_numerica"] = convention
        if info.get("rol") in METRIC_ROLES:
            info["politica_nulos"] = "preservados (nunca se imputa 0 en montos)"

    avisos: list[str] = []
    has_id_column = any(_is_id_like(col) for col in df.columns)
    duplicados_criterio = "fila_completa_normalizada"
    if problems["duplicados"] > 0 and not has_id_column:
        avisos.append(
            f"Se detectaron {problems['duplicados']} fila(s) idénticas y el archivo no "
            "trae una columna identificadora (folio, boleta, ID). Si dos ventas "
            "legítimas pueden ser idénticas, revisa antes de eliminar: en la descarga "
            "quedan marcadas."
        )
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
        "filas_duplicadas_a_eliminar": problems["duplicados"] if active["duplicados"] else 0,
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

    if apply:
        miss_cache, date_cache, num_cache = caches
        if active["columnas_vacias"] and empty_columns:
            df = df.drop(columns=empty_columns)
        if active["duplicados"]:
            df = df[~duplicated_mask].reset_index(drop=True)

        for col in df.columns:
            if col not in scoped_cols:
                continue
            ctype = column_types.get(col, "texto")
            if ctype == "fecha" and active["fechas"]:
                # Las fechas irreparables quedan vacías (señalizadas en la descarga).
                df[col] = df[col].map(
                    lambda v: "" if not is_missing(v) and parse_date(v) is None else v
                )
            elif ctype == "numero" and active["tipos"]:
                df[col] = df[col].map(
                    lambda v: "" if not is_missing(v) and parse_number(v) is None else v
                )
            # §5.1: sin imputación de nulos — nunca "0" en montos/costos/cantidades.

        rows_after, cols_after = len(df), len(df.columns)
        remaining = _detect_problems(
            df, column_types, text_changes=0, roles_by_col=roles_by_col, scoped_cols=scoped_cols
        )
        remaining.pop("_columnas_vacias_nombres")
        remaining.pop("_duplicados_mask")
        remaining.pop("_por_columna")
        remaining.pop("_caches")
        # Los nulos preservados por diseño ya están catalogados por columna en el
        # reporte de calidad: la calidad post-limpieza mide problemas ESTRUCTURALES
        # pendientes (fechas/tipos irreparables no tratados, duplicados restantes).
        remaining_cells = (
            remaining["fechas_invalidas"]
            + remaining["tipos_incorrectos"]
            + remaining["duplicados"] * max(cols_after, 1)
        )
        quality_after = _quality(remaining_cells, rows_after * max(cols_after, 1))

    return {
        "resumen": {
            "filas_antes": rows_before,
            "filas_despues": rows_after,
            "columnas_antes": cols_before,
            "columnas_despues": cols_after,
            "calidad_antes": quality_before,
            "calidad_despues": quality_after,
            "aplicado": apply,
        },
        "problemas": problems,
        "correcciones": corrections,
        "reglas_activas": active,
        "preview": preview,
        "estandarizacion": std_report["cambios"],
        "column_types": column_types,
        "mapeo": roles,
        "reporte_calidad": per_column,
        "avisos": avisos,
        "duplicados_criterio": duplicados_criterio,
        "fusiones_texto": fusiones,
        "_df_limpio": df if apply else None,
    }
