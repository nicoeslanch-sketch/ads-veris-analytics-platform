"""Value purchase lines with unambiguous document metadata, never a raw join."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite

import pandas as pd

from .mapping import norm_key, strip_accents_lower
from .metrics import detect_currency
from .quality import numeric_series
from .standardize import map_unique, parse_date


def _column(columns, *aliases):
    units = ('clp', 'uf', 'usd', 'eur', 'ars', 'pen', 'cop', 'mxn', 'gbp')
    matches = [str(col) for col in columns if norm_key(col) in aliases or any(
        norm_key(col) == alias + unit for alias in aliases for unit in units)]
    return matches[0] if len(matches) == 1 else None


def _key(value):
    return None if pd.isna(value) else str(value).strip().casefold() or None


def _fields(frame):
    return {
        'date': _column(frame.columns, 'fechacompra', 'purchasedate', 'fecha', 'fechadocumento'),
        'status': _column(frame.columns, 'estadocompra', 'estado', 'status'),
        'provider': _column(frame.columns, 'idproveedor', 'proveedorid', 'supplierid'),
        'branch': _column(frame.columns, 'idsucursal', 'sucursalid', 'branchid'),
        'currency': _column(frame.columns, 'moneda', 'currency', 'divisa'),
    }


def _attribute(values, field):
    if field == 'date':
        return pd.to_datetime(map_unique(values.astype(str), parse_date), errors='coerce')
    if field == 'status':
        return values.map(lambda value: None if pd.isna(value) else strip_accents_lower(str(value)).strip() or None)
    return values.map(_key)


def analyze_purchase_documents(
    frames: dict[str, pd.DataFrame], *, currency: str,
    period_mask: Callable[[pd.Series], pd.Series], dimensional_filter: bool = False,
    currency_hints: dict | None = None,
) -> dict | None:
    headers, details, warnings = [], [], []
    for name, frame in frames.items():
        identity = _column(frame.columns, 'idcompra', 'compraid', 'purchaseid')
        if not identity:
            continue
        if sum(norm_key(column) in {'moneda', 'currency', 'divisa'} for column in frame.columns) > 1:
            warnings.append('Hay hojas de compras con varias columnas de moneda; no se elige una arbitrariamente.')
            continue
        fields = _fields(frame)
        quantity = _column(frame.columns, 'cantidad', 'quantity', 'unidades')
        cost = _column(frame.columns, 'costounitariocompra', 'costounitario', 'unitcost', 'purchaseunitcost', 'costounitarioneto')
        product = _column(frame.columns, 'idproducto', 'productoid', 'skuproducto', 'sku', 'productid')
        line = _column(frame.columns, 'linea', 'numerolinea', 'linenumber', 'lineid', 'detallecompraid')
        rows = pd.DataFrame({'id': frame[identity].map(_key)})
        for field, column in fields.items():
            rows[field] = _attribute(frame[column], field) if column else pd.NaT if field == 'date' else None
        rows['sheet'] = name
        if not quantity and not product and not cost and fields['date']:
            headers.append(rows)
        elif quantity and cost and product and line:
            rows['quantity'] = numeric_series(frame, quantity)
            rows['cost'] = numeric_series(frame, cost)
            rows['product'] = frame[product].map(_key)
            rows['line'] = frame[line].map(_key)
            source_rows = frame.attrs.get('adsveris_source_rows', frame.attrs.get('source_rows', ()))
            rows['source_row'] = list(source_rows) if len(source_rows) == len(frame) else range(2, len(frame) + 2)
            detection = detect_currency(frame[cost], header_hints=(cost.replace('_', ' '),))
            hint = (currency_hints or {}).get(name)
            hint_currency = hint.get('dominante') if isinstance(hint, dict) else getattr(hint, 'dominante', None)
            hint_mixed = hint.get('mixta', False) if isinstance(hint, dict) else getattr(hint, 'mixta', False)
            hint_detected = hint.get('detectadas') if isinstance(hint, dict) else getattr(hint, 'detectadas', ())
            rows['source_currency'] = (hint_currency if hint_detected else None) or (detection.dominante if detection.detectadas else None)
            rows['mixed_currency'] = bool(hint_mixed or detection.mixta)
            details.append(rows)
        else:
            warnings.append('Hay hojas de compras cuya estructura no permite reconstruir lineas verificables.')
    if not headers or not details:
        return None

    reference = pd.concat(headers, ignore_index=True)
    rows = pd.concat(details, ignore_index=True)
    fields = ['date', 'status', 'provider', 'branch', 'currency']
    variants = reference.drop(columns='sheet').drop_duplicates()
    conflicts = set(variants.loc[variants.id.notna() & variants.id.duplicated(False), 'id'])
    safe = variants.loc[variants.id.notna() & ~variants.id.isin(conflicts)].set_index('id')
    matched = rows.id.notna() & rows.id.isin(safe.index)
    attribute_conflict = pd.Series(False, index=rows.index)
    for field in fields:
        inherited = rows.id.map(safe[field])
        attribute_conflict |= matched & rows[field].notna() & inherited.notna() & rows[field].ne(inherited)
        rows[field] = rows[field].where(rows[field].notna(), inherited)
    matched &= ~attribute_conflict
    # No line copies are removed. Conflicting IDs cannot choose a winner.
    signature = ['id', 'line', 'product', 'quantity', 'cost', *fields]
    line_variants = rows.drop_duplicates(signature)
    conflicting_lines = line_variants.loc[line_variants.duplicated(['id', 'line'], False), ['id', 'line']]
    conflict_index = pd.MultiIndex.from_frame(conflicting_lines)
    line_conflict = pd.Series(pd.MultiIndex.from_frame(rows[['id', 'line']]).isin(conflict_index), index=rows.index)
    repeated = rows.duplicated(signature, False)

    cancelled = rows.status.str.contains(r'\b(?:anulad|cancelad|void)\w*', na=False)
    known_status = rows.status.str.fullmatch(
        r'(?:recibid[oa]|recepcionad[oa]|pendiente|aprobad[oa]|emitid[oa]|pagad[oa]|completad[oa]|ordenad[oa])', na=False)
    in_period = period_mask(rows.date) & rows.date.notna()
    # Unresolved identity/date/status cannot be silently excluded from coverage.
    unresolved = ~matched | rows.date.isna() | (~known_status & ~cancelled)
    scope = unresolved | (in_period & ~cancelled)
    finite_quantity = rows.quantity.between(0, float('inf'), inclusive='left')
    finite_cost = rows.cost.between(0, float('inf'), inclusive='left')
    amount = (rows.quantity * rows.cost).replace([float('inf'), float('-inf')], float('nan'))
    eligible = (matched & known_status & in_period & ~cancelled & ~line_conflict
                & rows.line.notna() & rows['product'].notna() & finite_quantity & finite_cost & amount.notna())
    header_currency = rows.currency.fillna(rows.source_currency).fillna('CLP').str.upper()
    currency_conflict = (rows.mixed_currency | header_currency.ne(currency.upper())
                         | (rows.source_currency.notna() & rows.source_currency.astype('string').str.upper().ne(currency.upper())))
    blocked_currency = bool((scope & currency_conflict).any())
    blocked = dimensional_filter or blocked_currency
    missing_headers = reference.id.isna().sum()
    unlinked_headers = safe.loc[~safe.index.isin(rows.id)]
    header_in_scope = period_mask(unlinked_headers.date) & unlinked_headers.date.notna()
    header_cancelled = unlinked_headers.status.str.contains(r'\b(?:anulad|cancelad|void)\w*', na=False)
    missing_details = int((header_in_scope & ~header_cancelled | unlinked_headers.date.isna()).sum())
    uncertain_headers = int(missing_headers) + len(conflicts) + missing_details
    if unresolved.any():
        warnings.append(f'Hay {int(unresolved.sum())} de {len(rows)} lineas sin cabecera, fecha o estado verificables; su importe no se incorpora al subtotal.')
    if line_conflict.any():
        warnings.append('Hay valores contradictorios para un mismo ID de compra y linea; no se elige uno arbitrariamente.')
    if (scope & repeated).any():
        warnings.append('Se conservan copias repetidas de lineas por la decision sobre duplicados; pueden inflar el subtotal.')
    if uncertain_headers:
        warnings.append('Hay cabeceras sin detalle, sin ID o contradictorias; no se puede afirmar cobertura documental completa.')
    if (scope & ~eligible).any():
        warnings.append('Subtotal parcial: hay lineas del alcance sin cantidad, costo o vinculo validos; no se completan con cero.')
    if blocked_currency:
        warnings.append('Las compras contienen monedas incompatibles con esta vista; no se suman ni convierten.')
    if dimensional_filter:
        warnings.append('La valoracion de compras no esta publicada para este segmento; no se sustituye por el total general.')
    value = float(amount[eligible].sum()) if eligible.any() and not blocked else None
    if value is not None and not isfinite(value):
        value = None
        warnings.append('El importe excede el rango numerico admitido; no se publica un total invalido.')
    partial = bool(warnings)
    warnings.append('Cantidad por costo unitario declarado, incluidas compras pendientes no anuladas. No acredita pagos ni importe neto de IVA o descuentos.')
    valued_dates = rows.loc[eligible, 'date']
    relation = {
        'relacion': 'Detalle de compras -> Cabeceras de compra', 'filas': len(rows),
        'validas': int(matched.sum()), 'huerfanas': int((~matched & rows.id.notna()).sum()),
        'sin_clave': int(rows.id.isna().sum()), 'cobertura_pct': round(float(matched.mean()) * 100, 2) if len(rows) else 0,
        'cabeceras_conflictivas': int(rows.id.isin(conflicts).sum()),
        'atributos_conflictivos': int(attribute_conflict.sum()),
        'copias_cabecera_no_multiplicadas': len(reference) - len(variants),
        'ejemplos': [str(value) for value in rows.loc[~matched, 'id'].head(8)],
        'ubicaciones': [{'hoja': row.sheet, 'fila': int(row.source_row), 'clave': str(row.id)}
                        for row in rows.loc[~matched].head(8).itertuples()],
    }
    return {
        'valor': round(value, 2) if value is not None else None,
        'estado': 'unavailable' if value is None else 'partial' if partial else 'available',
        'cobertura_datos_pct': round(float(eligible.sum() / scope.sum() * 100), 2) if scope.any() and not blocked else None,
        'advertencias': warnings, 'fuentes': sorted(set(reference.sheet) | set(rows.sheet)),
        'formula': 'Suma de cantidad por costo unitario declarado en lineas vinculadas por ID a compras no anuladas',
        'relacion': relation, 'lineas_valorizadas': int(eligible.sum()),
        'lineas_del_alcance': int(scope.sum()), 'cabeceras_sin_detalle': missing_details,
        'periodo_actual': {
            'desde': valued_dates.min().strftime('%Y-%m-%d') if not valued_dates.empty else None,
            'hasta': valued_dates.max().strftime('%Y-%m-%d') if not valued_dates.empty else None,
        },
    }
