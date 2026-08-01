"""Reductor especializado de Archivo D a un máximo de una fila por matrícula."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ..codebooks import CodebookResult, normalize_code
from ..ingestion import iter_csv_chunks


def selected_status_codes(codebook: CodebookResult) -> frozenset[str]:
    markers = ("SELECCIONADA/O PARA ESTA CARRERA", "SELECCIONADO/A PARA ESTA CARRERA")
    return frozenset(
        code for code, label in codebook.mapping.items()
        if any(marker in label.upper() for marker in markers)
    )


def resolve_preferences_frame(
    matricula: pd.DataFrame,
    preferences: pd.DataFrame,
    allowed_statuses: frozenset[str],
) -> tuple[pd.DataFrame, dict[str, int]]:
    authority = {
        str(row.ID_aux).strip(): normalize_code(row.CODIGO)
        for row in matricula[["ID_aux", "CODIGO"]].itertuples(index=False)
    }
    candidate_counts: Counter[str] = Counter()
    candidate_rows: dict[str, tuple[str, str, str, str]] = {}
    for row in preferences[["ID_aux", "COD_CARRERA_PREF", "ESTADO_PREF", "ORDEN_PREF", "PTJE_PREF"]].itertuples(index=False):
        key = str(row.ID_aux).strip()
        if key not in authority:
            continue
        status = normalize_code(row.ESTADO_PREF)
        code = normalize_code(row.COD_CARRERA_PREF)
        if code != authority[key] or status not in allowed_statuses:
            continue
        candidate_counts[key] += 1
        if candidate_counts[key] == 1:
            candidate_rows[key] = (key, code, status, str(row.ORDEN_PREF), str(row.PTJE_PREF))
        else:
            candidate_rows.pop(key, None)
    records = [
        {
            "ID_aux": key,
            "d_codigo_carrera": values[1],
            "d_estado_pref": values[2],
            "d_orden_pref": values[3],
            "d_ptje_pref": values[4],
            "d_resolution": "d_match_unique",
        }
        for key, values in candidate_rows.items()
    ]
    resolved = pd.DataFrame.from_records(records)
    ambiguous = sum(1 for count in candidate_counts.values() if count > 1)
    unique = len(candidate_rows)
    return resolved, {
        "d_match_unique": unique,
        "d_ambiguous": ambiguous,
        "d_no_match": len(authority) - unique - ambiguous,
    }


def resolve_preferences_csv(
    matricula: pd.DataFrame,
    path: Path,
    allowed_statuses: frozenset[str],
    *,
    chunk_rows: int | None = None,
    checkpoint: Callable[[], None] | None = None,
    include_records: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    authority = {
        str(row.ID_aux).strip(): normalize_code(row.CODIGO)
        for row in matricula[["ID_aux", "CODIGO"]].itertuples(index=False)
    }
    candidate_counts: Counter[str] = Counter()
    candidate_rows: dict[str, tuple[str, str, str, str, str]] = {}
    rows_read = rows_in_universe = chunks = 0
    for chunk in iter_csv_chunks(
        path,
        ["ID_aux", "COD_CARRERA_PREF", "ESTADO_PREF", "ORDEN_PREF", "PTJE_PREF"],
        chunk_rows=chunk_rows,
        checkpoint=checkpoint,
    ):
        chunks += 1
        rows_read += len(chunk)
        keys = chunk["ID_aux"].astype("string").str.strip()
        in_universe = keys.isin(authority)
        rows_in_universe += int(in_universe.sum())
        scoped = chunk.loc[in_universe].copy()
        scoped["ID_aux"] = keys.loc[in_universe]
        scoped["COD_CARRERA_PREF"] = scoped["COD_CARRERA_PREF"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
        scoped["ESTADO_PREF"] = scoped["ESTADO_PREF"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
        authority_codes = scoped["ID_aux"].map(authority).astype("string")
        scoped = scoped.loc[
            scoped["COD_CARRERA_PREF"].eq(authority_codes)
            & scoped["ESTADO_PREF"].isin(allowed_statuses)
        ]
        for row in scoped.itertuples(index=False):
            key = str(row.ID_aux).strip()
            status = str(row.ESTADO_PREF)
            code = str(row.COD_CARRERA_PREF)
            candidate_counts[key] += 1
            if candidate_counts[key] == 1:
                candidate_rows[key] = (key, code, status, str(row.ORDEN_PREF), str(row.PTJE_PREF))
            else:
                candidate_rows.pop(key, None)
        del authority_codes, scoped, in_universe, keys, chunk
    records = (
        [
            {"ID_aux": key, "d_codigo_carrera": values[1], "d_estado_pref": values[2], "d_orden_pref": values[3], "d_ptje_pref": values[4], "d_resolution": "d_match_unique"}
            for key, values in candidate_rows.items()
        ]
        if include_records
        else []
    )
    ambiguous = sum(1 for count in candidate_counts.values() if count > 1)
    unique = len(candidate_rows)
    return pd.DataFrame.from_records(records), {
        "d_rows_read": rows_read,
        "d_rows_in_matricula_universe": rows_in_universe,
        "d_chunks": chunks,
        "d_match_unique": unique,
        "d_ambiguous": ambiguous,
        "d_no_match": len(authority) - unique - ambiguous,
    }
