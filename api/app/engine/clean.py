"""Detección y corrección de problemas del dataset (SPEC §6, POST /clean).

Detecta: duplicados, valores nulos, fechas inválidas, textos inconsistentes,
tipos de dato incorrectos, columnas vacías y valores fuera de rango.
Con `apply=True` corrige lo que las reglas activas permiten; con `apply=False`
solo reporta (vista previa de "antes de la limpieza").
"""

import pandas as pd

from .mapping import detect_column_roles
from .mapping import dedup_norm_key
from .standardize import is_missing, parse_date, parse_number, standardize_dataframe

PREVIEW_ROWS = 8

DEFAULT_RULES = {
    "fechas": True,            # Estándar de formato de fecha
    "textos": True,            # Unificar texto
    "duplicados": True,        # Eliminar duplicados
    "tipos": True,             # Convertir tipos de dato
    "nulos": True,             # Manejar valores nulos
    "columnas_vacias": True,   # Eliminar columnas vacías
    "fuera_de_rango": True,    # Validar rangos y outliers
}


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


def _detect_problems(df: pd.DataFrame, column_types: dict[str, str], text_changes: int) -> dict:
    empty_columns = [col for col in df.columns if all(is_missing(v) for v in df[col])]
    duplicated_mask = _dedup_mask(df)

    nulls = 0
    invalid_dates = 0
    wrong_types = 0
    out_of_range = 0

    for col in df.columns:
        if col in empty_columns:
            continue
        values = df[col]
        nulls += int(values.map(is_missing).sum())
        ctype = column_types.get(col, "texto")
        if ctype == "fecha":
            invalid_dates += int(
                values.map(lambda v: not is_missing(v) and parse_date(v) is None).sum()
            )
        elif ctype == "numero":
            parsed = values.map(lambda v: None if is_missing(v) else parse_number(v))
            wrong_types += int(
                values.map(lambda v: not is_missing(v)).sum() - parsed.notna().sum()
            )
            numbers = parsed.dropna()
            if len(numbers) >= 8:
                q1, q3 = numbers.quantile(0.25), numbers.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
                    out_of_range += int(((numbers < lower) | (numbers > upper)).sum())

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
    }


def _preview_with_issues(df: pd.DataFrame, column_types: dict[str, str]) -> dict:
    """Primeras filas + coordenadas de celdas problemáticas para resaltarlas."""
    preview = df.head(PREVIEW_ROWS)
    duplicated_mask = _dedup_mask(df)
    issues: list[dict] = []
    for row_index in range(len(preview)):
        if bool(duplicated_mask.iloc[row_index]):
            issues.append({"fila": row_index, "columna": "*", "tipo": "duplicado"})
        for col in preview.columns:
            value = preview.iloc[row_index][col]
            if is_missing(value):
                issues.append({"fila": row_index, "columna": col, "tipo": "nulo"})
                continue
            ctype = column_types.get(col, "texto")
            if ctype == "fecha" and parse_date(value) is None:
                issues.append({"fila": row_index, "columna": col, "tipo": "fecha_invalida"})
            elif ctype == "numero" and parse_number(value) is None:
                issues.append({"fila": row_index, "columna": col, "tipo": "tipo_incorrecto"})
    return {
        "columnas": list(preview.columns),
        "filas": [[str(v) for v in row] for row in preview.itertuples(index=False, name=None)],
        "issues": issues,
    }


def analyze_and_clean(df_original: pd.DataFrame, rules: dict | None, apply: bool) -> dict:
    active = {**DEFAULT_RULES, **(rules or {})}

    # La limpieza siempre parte de datos estandarizados (idempotente).
    df, std_report = standardize_dataframe(df_original)
    column_types = std_report["column_types"]
    text_changes = std_report["cambios"]["textos_normalizados"]

    rows_before, cols_before = len(df), len(df.columns)
    total_cells = rows_before * cols_before

    problems = _detect_problems(df, column_types, text_changes)
    empty_columns: list[str] = problems.pop("_columnas_vacias_nombres")
    duplicated_mask: pd.Series = problems.pop("_duplicados_mask")

    preview = _preview_with_issues(df, column_types)

    problem_cells = (
        problems["valores_nulos"]
        + problems["fechas_invalidas"]
        + problems["tipos_incorrectos"]
        + problems["duplicados"] * cols_before
    )
    quality_before = _quality(problem_cells, total_cells)

    corrections = {
        "filas_duplicadas_a_eliminar": problems["duplicados"] if active["duplicados"] else 0,
        "valores_nulos_a_reemplazar": problems["valores_nulos"] if active["nulos"] else 0,
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
        if active["columnas_vacias"] and empty_columns:
            df = df.drop(columns=empty_columns)
        if active["duplicados"]:
            df = df[~duplicated_mask].reset_index(drop=True)

        for col in df.columns:
            ctype = column_types.get(col, "texto")
            if ctype == "fecha" and active["fechas"]:
                # Las fechas irreparables quedan vacías (y cuentan como nulos tratados).
                df[col] = df[col].map(lambda v: "" if not is_missing(v) and parse_date(v) is None else v)
            elif ctype == "numero":
                if active["tipos"]:
                    df[col] = df[col].map(
                        lambda v: "" if not is_missing(v) and parse_number(v) is None else v
                    )
                if active["nulos"]:
                    df[col] = df[col].map(lambda v: "0" if is_missing(v) else v)

        rows_after, cols_after = len(df), len(df.columns)
        remaining = _detect_problems(df, column_types, text_changes=0)
        remaining.pop("_columnas_vacias_nombres")
        remaining.pop("_duplicados_mask")
        remaining_cells = (
            remaining["valores_nulos"]
            + remaining["fechas_invalidas"]
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
        "mapeo": detect_column_roles(list(df.columns)),
        "_df_limpio": df if apply else None,
    }
