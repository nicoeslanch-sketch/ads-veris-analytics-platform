"""Read-only, cardinality-preserving sales header/detail enrichment.

Only explicitly identified sales documents are linked. Monetary header totals
never travel to line items, and conflicting references never win arbitrarily.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .mapping import norm_key, resolve_mapping, strip_accents_lower
from .quality import find_column
from .standardize import parse_date


MATCH_COLUMN = "_ads_document_match"


def document_id(columns) -> str | None:
    return next((str(col) for col in columns if norm_key(col) in {
        "idventa", "saleid", "salesid",
    }), None)


def line_number(columns) -> str | None:
    return next((str(col) for col in columns if norm_key(col) in {
        "linea", "numerolinea", "nrolinea", "line", "linenumber", "lineid", "idlinea",
    }), None)


def _key(value) -> str | None:
    if pd.isna(value):
        return None
    return str(value).strip().casefold() or None


def _fields(frame: pd.DataFrame) -> dict[str, str]:
    candidates = {
        "FechaVenta": find_column(frame.columns, "fecha", "venta")
            or find_column(frame.columns, "fecha"),
        "IDCliente": find_column(frame.columns, "id", "cliente"),
        "IDSucursal": find_column(frame.columns, "id", "sucursal"),
        "IDVendedor": find_column(frame.columns, "id", "vendedor"),
        "EstadoVenta": find_column(frame.columns, "estado", "venta")
            or find_column(frame.columns, "estado"),
        "Canal": find_column(frame.columns, "canal"),
        "MedioPago": find_column(frame.columns, "medio", "pago"),
    }
    return {name: column for name, column in candidates.items() if column}


def _attribute(value, name: str) -> str | None:
    if pd.isna(value) or not str(value).strip():
        return None
    if name == "FechaVenta":
        parsed = parse_date(str(value))
        return str(parsed) if parsed is not None else _key(value)
    return strip_accents_lower(str(value)).strip()


@dataclass
class DocumentModel:
    frames: dict[str, pd.DataFrame]
    mappings: dict[str, dict[str, str]]
    headers: set[str]
    details: set[str]
    relations: list[dict]


def prepare_document_lines(
    frames: dict[str, pd.DataFrame], mappings: dict[str, dict[str, str]],
) -> DocumentModel:
    """Prepare analytical copies only; original rows and exports stay intact."""
    model = DocumentModel(dict(frames), dict(mappings), set(), set(), [])
    headers = []
    for name, frame in frames.items():
        key = document_id(frame.columns)
        roles = resolve_mapping(list(frame.columns), mappings.get(name))
        fields = _fields(frame)
        if not key or "FechaVenta" not in fields or any(
            role in roles for role in ("monto", "cantidad", "producto")
        ):
            continue
        reference = pd.DataFrame({"_key": frame[key].map(_key)})
        for target, source in fields.items():
            reference[target] = frame[source].map(lambda v: _attribute(v, target))
        reference["_header_sheet"] = name
        headers.append(reference)
        model.headers.add(name)
    if not headers:
        return model

    reference = pd.concat(headers, ignore_index=True)
    reference = reference.loc[reference["_key"].notna()]
    metadata = [c for c in reference.columns if c not in {"_key", "_header_sheet"}]
    variants = reference.drop(columns="_header_sheet").drop_duplicates()
    conflicting = set(variants.loc[variants["_key"].duplicated(False), "_key"])
    safe = reference.loc[~reference["_key"].isin(conflicting)].drop_duplicates("_key")
    safe = safe.set_index("_key")
    all_keys = set(reference["_key"])

    for name, frame in frames.items():
        key = document_id(frame.columns)
        roles = resolve_mapping(list(frame.columns), mappings.get(name))
        if name in model.headers or not key or not all(
            role in roles for role in ("monto", "cantidad", "producto")
        ):
            continue
        keys = frame[key].map(_key)
        matched = keys.notna() & keys.isin(safe.index)
        attributes_conflict = pd.Series(False, index=frame.index)
        enriched = frame.copy()
        existing = _fields(frame)
        for attribute in metadata:
            source = keys.map(safe[attribute])
            target = existing.get(attribute, attribute)
            if target in frame.columns:
                current = frame[target].map(lambda v: _attribute(v, attribute))
                attributes_conflict |= matched & current.notna() & source.notna() & current.ne(source)
                enriched[target] = frame[target].where(current.notna(), source)
            else:
                enriched[target] = source
        matched &= ~attributes_conflict
        enriched[MATCH_COLUMN] = matched.astype(int)
        model.frames[name] = enriched
        model.mappings[name] = resolve_mapping(list(enriched.columns), mappings.get(name))
        model.details.add(name)
        missing = keys.isna()
        unresolved = ~matched & ~missing
        source_rows = frame.attrs.get("adsveris_source_rows", frame.attrs.get("source_rows", ()))
        positions = [pos for pos, value in enumerate(unresolved) if value][:8]
        model.relations.append({
            "relacion": f"{name} -> Cabeceras de venta",
            "hojas_cabecera": sorted(model.headers),
            "filas": len(frame), "validas": int(matched.sum()),
            "huerfanas": int(unresolved.sum()), "sin_clave": int(missing.sum()),
            "cabeceras_conflictivas": int(keys.isin(conflicting).sum()),
            "atributos_conflictivos": int(attributes_conflict.sum()),
            "id_inexistente": int((keys.notna() & ~keys.isin(all_keys)).sum()),
            "copias_cabecera_no_multiplicadas": int(len(reference) - len(variants)),
            "cobertura_pct": round(float(matched.mean()) * 100, 1) if len(frame) else 0,
            "ejemplos": [str(frame.iloc[pos][key]) for pos in positions],
            "ubicaciones": [{"hoja": name, "fila": int(source_rows[pos])
                if len(source_rows) == len(frame) else pos + 2,
                "clave": str(frame.iloc[pos][key])} for pos in positions],
        })
    return model
