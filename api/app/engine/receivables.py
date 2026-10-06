"""Read-only receivable balances, separate from sales and payment movements."""

from __future__ import annotations

import pandas as pd

from .mapping import norm_key, strip_accents_lower
from .metrics import detect_currency
from .quality import numeric_series
from .standardize import map_unique, parse_date


def _column(columns, *aliases: str) -> str | None:
    keys = set(aliases)
    units = ("clp", "uf", "usd", "eur", "ars", "pen", "cop", "mxn", "gbp")
    return next((str(c) for c in columns if norm_key(c) in keys or any(
        norm_key(c) == alias + unit for alias in keys for unit in units
    )), None)


def is_receivable_sheet(name: str, frame: pd.DataFrame) -> bool:
    balance = _column(frame.columns, "saldo", "saldopendiente", "saldoabierto", "balance")
    identity = _column(frame.columns, "idcxc", "idcuentaporcobrar", "receivableid")
    label = norm_key(name)
    return bool(balance and (identity or "cxc" in label or "cuentasporcobrar" in label))


def receivable_document_key(value: object) -> str | None:
    if pd.isna(value):
        return None
    # Leading zeroes distinguish documents. Never use numeric/fuzzy key coercion.
    return str(value).strip().casefold() or None


def _dates(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return pd.to_datetime(map_unique(frame[column].astype(str), parse_date), errors="coerce")


def analyze_receivables(
    frames: dict[str, pd.DataFrame],
    valid_documents: set[str] | None,
    *,
    currency: str = "CLP",
    date_from: str | None = None,
    date_to: str | None = None,
    dimensional_filter: bool = False,
    currency_hints: dict | None = None,
) -> dict | None:
    if not frames:
        return None
    warnings = []
    parts = []
    locations = []
    blocked = False
    for name, frame in frames.items():
        balance = _column(frame.columns, "saldo", "saldopendiente", "saldoabierto", "balance")
        original = _column(frame.columns, "montooriginal", "montodocumento", "totaldocumento")
        document = _column(frame.columns, "idventa", "iddocumento", "saleid", "salesid")
        identity = _column(frame.columns, "idcxc", "idcuentaporcobrar", "receivableid") or document
        status = _column(frame.columns, "estadocxc", "estadopago", "estado", "status")
        cutoff = _column(frame.columns, "fechacorte", "fechasaldo", "asofdate")
        currency_col = _column(frame.columns, "moneda", "currency", "divisa")
        detection = detect_currency(
            frame[balance] if balance else None,
            frame[original] if original else None,
            frame[currency_col] if currency_col else None,
            header_hints=tuple(str(c).replace("_", " ") for c in (balance, original) if c),
        )
        hint = (currency_hints or {}).get(name)
        if isinstance(hint, dict):
            mixed_hint = hint.get("mixta", False)
            hinted_currency = hint.get("dominante")
        else:
            mixed_hint = getattr(hint, "mixta", False)
            hinted_currency = getattr(hint, "dominante", None)
        if detection.mixta or mixed_hint or (hinted_currency or detection.dominante) != currency.upper():
            blocked = True
            warnings.append("La cartera contiene monedas incompatibles con esta vista; no se suman ni convierten.")
        rows = pd.DataFrame(index=frame.index)
        rows["_id"] = frame[identity].map(receivable_document_key) if identity else None
        rows["_document"] = frame[document].map(receivable_document_key) if document else None
        rows["_balance"] = numeric_series(frame, balance)
        rows["_original"] = numeric_series(frame, original)
        rows["_has_original"] = original is not None
        rows["_status"] = frame[status].map(strip_accents_lower) if status else ""
        rows["_due"] = _dates(frame, _column(frame.columns, "fechavencimiento", "duedate"))
        rows["_issue"] = _dates(frame, _column(frame.columns, "fechaemision", "issuedate"))
        rows["_cut"] = _dates(frame, cutoff)
        rows["_has_cut"] = cutoff is not None
        parts.append(rows)
        source_rows = frame.attrs.get("adsveris_source_rows", frame.attrs.get("source_rows", ()))
        locations.extend({"hoja": name, "fila": int(source_rows[pos]) if pos < len(source_rows) else pos + 2}
                         for pos in range(len(frame)))

    rows = pd.concat(parts, ignore_index=True)
    source_rows = len(rows)
    cutoff_date = None
    has_cut = bool(rows["_has_cut"].all()) and source_rows > 0
    invalid_cut = int(rows["_cut"].isna().sum()) if has_cut else 0
    if invalid_cut:
        warnings.append("Hay filas con fecha de corte invalida; no se asignan a otro corte.")
    if dimensional_filter:
        blocked = True
        warnings.append("El saldo de cartera no esta publicado para este segmento; no se sustituye por el saldo general.")
    if has_cut:
        available = rows["_cut"].dropna()
        if date_to:
            upper = pd.Period(date_to, freq="M").end_time.normalize() if len(date_to) == 7 else pd.to_datetime(date_to)
            available = available[available.le(upper)]
        if available.empty:
            blocked = True
            warnings.append("No hay un corte de cartera valido dentro del limite solicitado.")
        else:
            cutoff_date = available.max()
            rows = rows.loc[rows["_cut"].eq(cutoff_date)].copy()
            if rows.empty:
                blocked = True
    elif date_from or date_to:
        blocked = True
        warnings.append("El archivo no declara fecha de corte del saldo. No se puede reconstruir una cartera historica filtrando fechas de emision.")
    else:
        warnings.append("Saldo declarado sin fecha de corte: no acredita un saldo historico ni la mora a una fecha especifica.")

    finite_balances = rows["_balance"].between(float("-inf"), float("inf"), inclusive="neither")
    declared = float(rows.loc[finite_balances, "_balance"].sum()) if finite_balances.any() else None
    unique = rows.drop_duplicates()
    duplicates = len(rows) - len(unique)
    conflicts = unique["_id"].notna() & unique["_id"].duplicated(keep=False)
    invalid_balance = unique["_balance"].isna() | ~unique["_balance"].between(0, float("inf"), inclusive="left")
    invalid_original = unique["_has_original"] & (
        unique["_original"].isna() | ~unique["_original"].between(0, float("inf"), inclusive="left")
        | unique["_balance"].gt(unique["_original"] + 0.01)
    )
    cancelled = unique["_status"].str.contains(r"\b(?:anulad|cancelad|void)\w*", regex=True, na=False)
    paid = unique["_status"].str.contains(r"\b(?:pagad|cobrad|saldad)\w*", regex=True, na=False)
    inconsistent = paid & unique["_balance"].gt(0)
    future_issue = unique["_issue"].gt(cutoff_date) if cutoff_date is not None else pd.Series(False, index=unique.index)
    known = unique["_document"].isin(valid_documents) if valid_documents is not None else pd.Series(False, index=unique.index)
    eligible = (
        known & unique["_id"].notna() & ~conflicts & ~invalid_balance
        & ~invalid_original & ~cancelled & ~inconsistent & ~future_issue
    )
    if valid_documents is None:
        blocked = True
        warnings.append("Faltan IDs explicitos de ventas para validar los documentos de cartera.")
    issue_count = int((~eligible).sum())
    if issue_count or duplicates:
        warnings.append("Se conservan las filas originales; saldos invalidos, IDs sin venta valida y conflictos no entran en la cartera validada. Las copias identicas se cuentan una vez.")
    open_rows = eligible & unique["_balance"].gt(0)
    overdue = unique["_status"].str.contains(r"\b(?:vencid|moros|atrasad)\w*", regex=True, na=False)
    if cutoff_date is not None:
        overdue = unique["_due"].lt(cutoff_date) | overdue
    due_known = (unique["_due"].notna() if cutoff_date is not None else pd.Series(False, index=unique.index)) | overdue
    missing_due = int((open_rows & ~due_known).sum())
    overdue_known = not open_rows.any() or bool(due_known[open_rows].any())
    if missing_due:
        warnings.append("La cartera vencida es parcial o no disponible: faltan fechas de vencimiento validas y un corte, o un estado vencido explicito.")
    examples = []
    for reason, mask in (
        ("Saldo invalido", invalid_balance),
        ("Monto original invalido o saldo superior al original", invalid_original),
        ("Cuenta pagada con saldo abierto", inconsistent),
        ("ID sin venta valida", ~known),
        ("Identidad de cuenta faltante", unique["_id"].isna()),
        ("Identidad de cuenta en conflicto", conflicts),
        ("Cuenta anulada", cancelled),
        ("Emision posterior al corte", future_issue),
    ):
        for index in unique.index[mask][:3]:
            if len(examples) < 12:
                examples.append({**locations[index], "motivo": reason})
    # An all-invalid/nonmatching source is unavailable, not a healthy zero.
    available_balance = not blocked and (bool(eligible.any()) or rows.empty and has_cut)
    coverage = float(eligible.sum()) / len(unique) * 100 if len(unique) else None
    return {
        "fuentes": list(frames),
        "saldo_declarado": round(declared, 2) if declared is not None and not blocked else None,
        "saldo_validado": round(float(unique.loc[eligible, "_balance"].sum()), 2) if available_balance else None,
        "saldo_vencido": round(float(unique.loc[open_rows & overdue, "_balance"].sum()), 2) if available_balance and overdue_known else None,
        "documentos_pendientes": int(open_rows.sum()) if available_balance else None,
        "fecha_corte": cutoff_date.date().isoformat() if cutoff_date is not None else None,
        "base": "ultimo_corte" if cutoff_date is not None else "saldo_declarado_sin_corte",
        "estado": "blocked" if blocked else "unavailable" if not available_balance else "partial" if issue_count or duplicates or invalid_cut or cutoff_date is None else "available",
        "estado_vencimiento": "blocked" if blocked else "unavailable" if not available_balance or not overdue_known else "partial" if missing_due else "available",
        "cobertura_datos_pct": round(coverage, 1) if coverage is not None else None,
        "filas_fuente": source_rows,
        "filas_corte": len(rows),
        "filas_corte_invalido": invalid_cut,
        "filas_validas": int(eligible.sum()),
        "filas_excluidas": issue_count,
        "ejemplos_problemas": examples,
        "filas_saldo_invalido": int(invalid_balance.sum()),
        "filas_original_invalido": int(invalid_original.sum()),
        "filas_estado_inconsistente": int(inconsistent.sum()),
        "filas_emision_posterior_corte": int(future_issue.sum()),
        "cuentas_sin_antiguedad_validable": missing_due,
        "filas_id_sin_venta_valida": int((~known).sum()),
        "filas_id_faltante": int(unique["_id"].isna().sum()),
        "ids_conflictivos": int(unique.loc[conflicts, "_id"].nunique()),
        "duplicados_excluidos_analisis": duplicates,
        "advertencias": list(dict.fromkeys(warnings)),
    }
