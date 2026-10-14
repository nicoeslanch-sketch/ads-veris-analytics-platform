"""Reconcile commercial document ledgers without flattening independent facts.

Schemas, not sheet names or control totals, identify sources. Every enrichment
is many-to-one; payments and returns are aggregated before balance arithmetic.
"""
from __future__ import annotations

import re
import pandas as pd

from .mapping import norm_key, strip_accents_lower
from .quality import numeric_series
from .standardize import map_unique, parse_date


SCHEMAS = {
    'sales': ('ventaid', 'fechaventa', 'estado', 'netodocumento', 'ivadocumento', 'totaldocumento'),
    'lines': ('detalleventaid', 'ventaid', 'productoid', 'loteid', 'cantidad', 'netolinea', 'ivalinea', 'totallinea', 'costolinea'),
    'credits': ('notacreditoid', 'ventaid', 'fechanota', 'netocreditado', 'ivacreditado', 'totalcreditado'),
    'returns': ('detalledevolucionid', 'notacreditoid', 'detalleventaid', 'productoid', 'loteid', 'cantidaddevuelta', 'netorevertido', 'ivarevertido', 'totalrevertido', 'costoreferencialrevertido', 'reingresastock'),
    'lots': ('loteid', 'productoid', 'sucursalid', 'fechaentrada', 'unidadesentrada', 'costounitarioneto'),
    'products': ('productoid', 'nombreproducto', 'categoriaid'),
    'categories': ('categoriaid', 'nombrecategoria'),
    'branches': ('sucursalid', 'nombre'),
    'employees': ('empleadoid', 'sucursalid', 'nombreempleado'),
    'collections': ('cobroid', 'ventaid', 'fechacobro', 'importebruto', 'comisionmediopago', 'depositoneto'),
    'refunds': ('reembolsoid', 'notacreditoid', 'ventaid', 'fechareembolso', 'montobruto'),
    'purchases': ('compraid', 'fechadocumento', 'proveedorid', 'neto', 'iva', 'totalbruto'),
    'purchase_lines': ('detallecompraid', 'compraid', 'productoid', 'netolinea', 'ivalinea', 'totallinea'),
    'supplier_payments': ('pagoproveedorid', 'compraid', 'fechapago', 'montobruto'),
    'expenses': ('gastoid', 'fechadocumento', 'neto', 'ivacredito', 'totalbruto', 'fechapago', 'estadopago'),
    'payroll': ('nominaid', 'empleadoid', 'periodomes', 'costoempresa', 'fechapago'),
    'loans': ('prestamoid', 'fechadesembolso', 'capitaloriginal'),
    'installments': ('cuotaid', 'prestamoid', 'fechapago', 'estadopago', 'interespagado', 'pagototal'),
}


def _column(value):
    value = norm_key(value)
    value = re.sub(r'(clp|usd|eur|uf)$', '', value)
    if value.startswith('id') and len(value) > 2:
        value = value[2:] + 'id'
    return value


def _keys(values):
    return values.astype('string').str.strip().str.casefold().replace('', pd.NA)


def _dates(values):
    return pd.to_datetime(map_unique(values.astype(str), parse_date), errors='coerce')


def analyze_relational_ledger(frames, *, date_from=None, date_to=None, currency_hints=None):
    sources, names, issues, currencies = {}, {}, [], set()
    for name, original in frames.items():
        if re.match(r'^(control|guia|parametr|diccionario|reporte)', norm_key(name)):
            continue
        columns = [_column(c) for c in original.columns]
        if len(columns) != len(set(columns)):
            continue
        for kind, required in SCHEMAS.items():
            if not set(required).issubset(columns):
                continue
            if kind in sources:
                issues.append(f'Varias hojas corresponden a {kind}; no se elige una arbitrariamente.')
                continue
            frame = original.rename(columns=dict(zip(original.columns, columns))).copy()
            names[kind] = name
            sources[kind] = frame
            hint = (currency_hints or {}).get(name)
            detected = hint.get('detectadas', []) if isinstance(hint, dict) else getattr(hint, 'detectadas', ())
            currencies.update(detected)
            for raw, col in zip(original.columns, columns):
                unit = re.search(r'(clp|usd|eur|uf)$', norm_key(raw))
                if unit:
                    currencies.add(unit.group(1).upper())
                if col.endswith('id'):
                    frame[col] = _keys(frame[col])
            pk = required[0]
            if frame[pk].isna().any() or frame[pk].duplicated().any():
                issues.append(f'{name}: la clave {pk} tiene ausentes o duplicados.')
    required = {'sales', 'lines', 'credits', 'returns', 'lots', 'products'}
    if not required.issubset(sources):
        return None
    if len(currencies) > 1:
        issues.append('Las fuentes tienen monedas diferentes; no se suman entre si.')
    currency = next(iter(currencies), 'CLP')
    links = [
        ('lines', 'ventaid', 'sales'), ('lines', 'productoid', 'products'),
        ('lines', 'loteid', 'lots'), ('credits', 'ventaid', 'sales'),
        ('returns', 'notacreditoid', 'credits'), ('returns', 'detalleventaid', 'lines'),
        ('returns', 'productoid', 'products'), ('returns', 'loteid', 'lots'),
        ('collections', 'ventaid', 'sales'), ('refunds', 'ventaid', 'sales'),
        ('refunds', 'notacreditoid', 'credits'), ('supplier_payments', 'compraid', 'purchases'),
        ('purchase_lines', 'compraid', 'purchases'), ('payroll', 'empleadoid', 'employees'),
        ('installments', 'prestamoid', 'loans'),
        ('lots', 'productoid', 'products'), ('lots', 'sucursalid', 'branches'),
        ('products', 'categoriaid', 'categories'), ('employees', 'sucursalid', 'branches'),
        ('purchase_lines', 'productoid', 'products'),
    ]
    relations = []
    for child, key, parent in links:
        if child not in sources or parent not in sources:
            continue
        valid = sources[child][key].notna() & sources[child][key].isin(sources[parent][key])
        relations.append({'desde': names[child], 'hasta': names[parent], 'clave': key,
                          'filas': len(valid), 'sin_correspondencia': int((~valid).sum())})
        if not valid.all():
            issues.append(f'{names[child]}: {int((~valid).sum())} referencias invalidas hacia {names[parent]}.')
    report = {'version': 1, 'available': False, 'moneda': currency,
              'fuentes': sorted(names.values()), 'relaciones': relations, 'advertencias': issues}
    if issues:
        return report

    def num(kind, column):
        values = numeric_series(sources[kind], column)
        if values.isna().any() or not values.abs().lt(float('inf')).all():
            issues.append(f'{names[kind]}: hay importes no interpretables en {column}.')
        return values

    for kind, frame in sources.items():
        for column in frame.columns:
            if column.startswith(('fecha', 'periodomes')):
                frame[column] = _dates(frame[column])
                if column in SCHEMAS[kind]:
                    required_date = pd.Series(True, index=frame.index)
                    if column == 'fechapago' and 'estadopago' in frame:
                        required_date = frame.estadopago.map(strip_accents_lower).str.fullmatch(r'pagad[oa]')
                    if frame.loc[required_date, column].isna().any():
                        issues.append(f'{names[kind]}: falta una fecha valida en {column}.')
        for column in SCHEMAS[kind]:
            if column.startswith(('neto', 'iva', 'total', 'costo', 'cantidad', 'importe', 'monto',
                                  'comision', 'deposito', 'unidades', 'capitaloriginal', 'interespagado', 'pagototal')):
                frame[column] = num(kind, column)
                if frame[column].lt(0).any():
                    issues.append(f'{names[kind]}: {column} contiene negativos en una fuente de importes positivos.')
    s, d, n, r, lots, products = (sources[k] for k in ('sales', 'lines', 'credits', 'returns', 'lots', 'products'))
    issued = s.estado.map(strip_accents_lower).eq('emitida')
    cancelled = s.estado.map(strip_accents_lower).str.fullmatch(r'anulad[oa]|cancelad[oa]|void')
    if not (issued | cancelled).all() or s.fechaventa.isna().any() or n.fechanota.isna().any():
        issues.append('Hay estados de venta o fechas sin interpretar; revisalos antes de conciliar.')
    stock_flag = r.reingresastock.map(lambda v: strip_accents_lower(str(v)))
    if not stock_flag.isin(['true', 'false', '1', '0', 'si', 'no', 'verdadero', 'falso']).all():
        issues.append('Hay decisiones de reingreso a stock sin interpretar.')
    stock_flag = stock_flag.isin(['true', '1', 'si', 'verdadero'])

    def reconcile(parent, child, key, pairs):
        for header_col, line_col in pairs:
            grouped = child.groupby(key)[line_col].sum(min_count=1)
            difference = parent[header_col] - parent[key].map(grouped)
            if difference.isna().any() or difference.abs().gt(0.01).any():
                issues.append(f'No concilian {header_col} y {line_col} por {key}.')
    reconcile(s, d, 'ventaid', [('netodocumento', 'netolinea'), ('ivadocumento', 'ivalinea'), ('totaldocumento', 'totallinea')])
    reconcile(n, r, 'notacreditoid', [('netocreditado', 'netorevertido'), ('ivacreditado', 'ivarevertido'), ('totalcreditado', 'totalrevertido')])
    if {'purchases', 'purchase_lines'}.issubset(sources):
        reconcile(sources['purchases'], sources['purchase_lines'], 'compraid',
                  [('neto', 'netolinea'), ('iva', 'ivalinea'), ('totalbruto', 'totallinea')])
    sale_ref = s.set_index('ventaid')
    line_ref = d.set_index('detalleventaid')
    note_ref = n.set_index('notacreditoid')
    lot_ref = lots.set_index('loteid')
    if not d.productoid.eq(d.loteid.map(lot_ref.productoid)).all():
        issues.append('Hay productos de venta que no corresponden al lote indicado.')
    for key in ('productoid', 'loteid'):
        if not r[key].eq(r.detalleventaid.map(line_ref[key])).all():
            issues.append(f'Una devolucion no coincide con {key} de su venta.')
    if not r.notacreditoid.map(note_ref.ventaid).eq(r.detalleventaid.map(line_ref.ventaid)).all():
        issues.append('Una nota de credito apunta a una venta distinta de su devolucion.')
    if not n.ventaid.isin(s.loc[issued, 'ventaid']).all():
        issues.append('Hay notas de credito sobre ventas no emitidas.')
    returned_qty = r.groupby('detalleventaid').cantidaddevuelta.sum()
    if returned_qty.gt(line_ref.cantidad.reindex(returned_qty.index)).any():
        issues.append('Las cantidades devueltas superan las cantidades vendidas.')
    expected_return_cost = r.detalleventaid.map(line_ref.costolinea / line_ref.cantidad.replace(0, float('nan'))) * r.cantidaddevuelta
    if expected_return_cost.isna().any() or (r.costoreferencialrevertido - expected_return_cost).abs().gt(0.01).any():
        issues.append('El costo revertido no corresponde al costo historico de la linea devuelta.')
    if n.fechanota.lt(n.ventaid.map(sale_ref.fechaventa)).any():
        issues.append('Hay notas de credito anteriores a la venta original.')
    for kind, net, tax, gross in [('sales', 'netodocumento', 'ivadocumento', 'totaldocumento'),
        ('lines', 'netolinea', 'ivalinea', 'totallinea'), ('credits', 'netocreditado', 'ivacreditado', 'totalcreditado'),
        ('returns', 'netorevertido', 'ivarevertido', 'totalrevertido'), ('purchases', 'neto', 'iva', 'totalbruto'),
        ('expenses', 'neto', 'ivacredito', 'totalbruto')]:
        if kind in sources:
            f = sources[kind]
            if (f[net] + f[tax] - f[gross]).abs().gt(0.01).any():
                issues.append(f'{names[kind]}: neto mas IVA no coincide con el total.')
    if 'collections' in sources:
        f = sources['collections']
        if (f.importebruto - f.comisionmediopago - f.depositoneto).abs().gt(0.01).any():
            issues.append('Los depositos no coinciden con cobros menos comisiones.')
    if 'refunds' in sources:
        f = sources['refunds']
        if not f.ventaid.eq(f.notacreditoid.map(note_ref.ventaid)).all():
            issues.append('Un reembolso no corresponde a la venta de su nota de credito.')
    if issues:
        return report

    sale_lines = d.loc[d.ventaid.isin(s.loc[issued, 'ventaid'])].copy()
    sale_lines['date'] = sale_lines.ventaid.map(sale_ref.fechaventa)
    movements = pd.DataFrame({'date': sale_lines.date, 'productoid': sale_lines.productoid,
        'sucursalid': sale_lines.loteid.map(lot_ref.sucursalid), 'ventaid': sale_lines.ventaid,
        'ventas': sale_lines.netolinea, 'costo': sale_lines.costolinea, 'unidades': sale_lines.cantidad})
    returned = pd.DataFrame({'date': r.notacreditoid.map(note_ref.fechanota), 'productoid': r.productoid,
        'sucursalid': r.loteid.map(lot_ref.sucursalid), 'ventaid': r.notacreditoid.map(note_ref.ventaid),
        'ventas': -r.netorevertido, 'costo': -r.costoreferencialrevertido.where(stock_flag, 0),
        'unidades': -r.cantidaddevuelta})
    movements = pd.concat([movements, returned], ignore_index=True)
    if movements.empty:
        issues.append('No hay movimientos comerciales emitidos para conciliar.')
        return report
    months = sorted(movements.date.dt.strftime('%Y-%m').dropna().unique().tolist())
    start = pd.to_datetime(date_from) if date_from else movements.date.min()
    end = pd.Period(date_to, freq='M').end_time if date_to and len(date_to) == 7 else pd.to_datetime(date_to) if date_to else movements.date.max().to_period('M').end_time
    if pd.isna(start) or pd.isna(end) or start > end:
        issues.append('El periodo solicitado no es valido.')
        return report

    def mask(frame, date, *, balance=False):
        valid = frame[date].notna() & frame[date].le(end)
        return valid if balance else valid & frame[date].ge(start)

    def total(kind, col, date, *, balance=False, paid=False):
        if kind not in sources:
            return None
        frame = sources[kind]
        selected = mask(frame, date, balance=balance)
        if paid:
            selected &= frame.estadopago.map(strip_accents_lower).str.fullmatch(r'pagad[oa]')
        return round(float(frame.loc[selected, col].sum()), 2)

    def diff(*values):
        return round(sum(values), 2) if all(v is not None for v in values) else None

    selected = movements.loc[mask(movements, 'date')].copy()
    selected['mes'] = selected.date.dt.strftime('%Y-%m')
    k = {'ventas_emitidas_netas': float(s.loc[issued & mask(s, 'fechaventa'), 'netodocumento'].sum()),
         'notas_credito_netas': total('credits', 'netocreditado', 'fechanota'),
         'ventas_netas': float(selected.ventas.sum()), 'costo_ventas_neto': float(selected.costo.sum()),
         'iva_debito_neto': diff(float(s.loc[issued & mask(s, 'fechaventa'), 'ivadocumento'].sum()), -total('credits', 'ivacreditado', 'fechanota')),
         'ventas_emitidas': int((issued & mask(s, 'fechaventa')).sum()),
         'ventas_anuladas': int((cancelled & mask(s, 'fechaventa')).sum()),
         'notas_credito': int(mask(n, 'fechanota').sum()), 'lineas_fisicas': len(d),
         'lineas_emitidas': int(mask(sale_lines, 'date').sum()),
         'unidades_emitidas': float(sale_lines.loc[mask(sale_lines, 'date'), 'cantidad'].sum()),
         'clientes_compradores': int(s.loc[issued & mask(s, 'fechaventa'), 'clienteid'].nunique()) if 'clienteid' in s else None}
    k['utilidad_bruta'] = k['ventas_netas'] - k['costo_ventas_neto']
    k['margen_bruto_pct'] = k['utilidad_bruta'] / k['ventas_netas'] * 100 if k['ventas_netas'] else None
    k['gastos_operacionales_netos'] = total('expenses', 'neto', 'fechadocumento')
    k['nominas'] = total('payroll', 'costoempresa', 'periodomes')
    k['comisiones_cobro'] = total('collections', 'comisionmediopago', 'fechacobro')
    k['intereses_pagados'] = total('installments', 'interespagado', 'fechapago', paid=True)
    operating = [k['gastos_operacionales_netos'], k['nominas'], k['comisiones_cobro'], k['intereses_pagados']]
    k['resultado_antes_impuestos'] = diff(k['utilidad_bruta'], *[-v if v is not None else None for v in operating])
    k['depositos_netos'] = total('collections', 'depositoneto', 'fechacobro')
    k['compras_netas'] = total('purchases', 'neto', 'fechadocumento')
    k['iva_credito'] = diff(total('purchases', 'iva', 'fechadocumento'), total('expenses', 'ivacredito', 'fechadocumento'))
    # Balances use all movements up to the cutoff, never just the selected month.
    def grouped(kind, key, value, date):
        if kind not in sources:
            return None
        f = sources[kind]
        return f.loc[mask(f, date, balance=True)].groupby(key)[value].sum()
    ar = s.loc[issued & mask(s, 'fechaventa', balance=True)].set_index('ventaid').totaldocumento.copy()
    for kind, value, date, sign in [('credits', 'totalcreditado', 'fechanota', -1),
        ('collections', 'importebruto', 'fechacobro', -1), ('refunds', 'montobruto', 'fechareembolso', 1)]:
        vals = grouped(kind, 'ventaid', value, date)
        if vals is None:
            ar = None
            break
        ar = ar.add(vals.reindex(ar.index).fillna(0) * sign)
    k['cuentas_por_cobrar'] = float(ar.sum()) if ar is not None else None
    purchase_balance = total('purchases', 'totalbruto', 'fechadocumento', balance=True)
    supplier_paid = total('supplier_payments', 'montobruto', 'fechapago', balance=True)
    k['cuentas_por_pagar'] = diff(purchase_balance, -supplier_paid if supplier_paid is not None else None)
    stocked = lots.loc[mask(lots, 'fechaentrada', balance=True)].set_index('loteid').copy()
    sold = sale_lines.loc[mask(sale_lines, 'date', balance=True)].groupby('loteid').cantidad.sum()
    stock_returns = r.loc[stock_flag & r.notacreditoid.map(note_ref.fechanota).le(end)].groupby('loteid').cantidaddevuelta.sum()
    stocked['stock'] = stocked.unidadesentrada - sold.reindex(stocked.index).fillna(0) + stock_returns.reindex(stocked.index).fillna(0)
    stocked['valor'] = stocked.stock * stocked.costounitarioneto
    if stocked.stock.lt(0).any():
        issues.append('El inventario presenta saldos negativos; revisa entradas y salidas por lote.')
        return report
    k['stock_unidades'] = float(stocked.stock.sum())
    k['inventario_valorizado'] = float(stocked.valor.sum())
    cash_out = [total('refunds', 'montobruto', 'fechareembolso'), total('supplier_payments', 'montobruto', 'fechapago'),
        total('expenses', 'totalbruto', 'fechapago', paid=True), total('payroll', 'costoempresa', 'fechapago'),
        total('installments', 'pagototal', 'fechapago', paid=True)]
    k['flujo_caja_antes_iva'] = diff(k['depositos_netos'], total('loans', 'capitaloriginal', 'fechadesembolso'),
                                  *[-v if v is not None else None for v in cash_out])

    product_ref = products.set_index('productoid')
    selected['producto'] = selected.productoid.map(product_ref.nombreproducto)
    selected['categoria'] = selected.productoid.map(product_ref.categoriaid)
    selected['categoriaid'] = selected['categoria']
    if 'categories' in sources:
        selected['categoria'] = selected.categoria.map(sources['categories'].set_index('categoriaid').nombrecategoria)
    selected['sucursal'] = selected.sucursalid
    if 'branches' in sources:
        selected['sucursal'] = selected.sucursalid.map(sources['branches'].set_index('sucursalid').nombre)
    def aggregate(col, key=None):
        rows = selected.groupby([key, col] if key else col, dropna=False)[['ventas', 'costo', 'unidades']].sum().reset_index()
        rows['utilidad'] = rows.ventas - rows.costo
        if col != 'mes':
            # Keep both ends of each supported ranking, not only revenue's
            # leaders: the highest-margin product may have few sales.
            indices = set()
            for measure in ('ventas', 'utilidad', 'unidades'):
                ordered = rows.sort_values(measure, kind='stable')
                indices.update(ordered.head(100).index)
                indices.update(ordered.tail(100).index)
            rows = rows.loc[sorted(indices)].sort_values('ventas', ascending=False)
        return rows.rename(columns={col: 'nombre' if col != 'mes' else 'mes', key: 'id'}).round(2).to_dict('records')
    inventory = stocked.groupby('productoid')[['stock', 'valor']].sum().reset_index()
    inventory['nombre'] = inventory.productoid.map(product_ref.nombreproducto)
    latest = sale_lines.loc[mask(sale_lines, 'date', balance=True)].groupby('productoid').date.max()
    inventory['dias_sin_venta'] = (end.normalize() - inventory.productoid.map(latest)).dt.days
    slow = inventory.loc[inventory.stock.gt(0) & (inventory.dias_sin_venta.ge(90) | inventory.dias_sin_venta.isna())]
    report.update({'available': True, 'kpis': {key: round(value, 2) if isinstance(value, float) else value for key, value in k.items()},
        'periodo': {'desde': start.date().isoformat(), 'hasta': end.date().isoformat(), 'meses': months},
        'mensual': aggregate('mes'), 'productos': aggregate('producto', 'productoid'),
        'categorias': aggregate('categoria', 'categoriaid'), 'sucursales': aggregate('sucursal', 'sucursalid'),
        'inventario_lento': slow.sort_values('valor', ascending=False).head(20).astype(object).where(pd.notna(slow), None).to_dict('records'),
        'criterios': ['Ventas y notas de credito por su fecha de emision; las notas no se trasladan al mes de la venta.',
                     'Costo historico de cada linea. Una devolucion revierte costo solo si reingresa a stock.',
                     'CxC, CxP e inventario acumulados al cierre; el flujo usa fechas de cobro y pago.',
                     'Los saldos corresponden a las fuentes observadas; requieren todas las entradas y saldos iniciales para representar el negocio completo.',
                     'Los desgloses incluyen los 100 mayores y menores grupos por ventas, utilidad y unidades; los totales usan todos los movimientos validos.',
                     'Resultado antes de impuestos y flujo antes de liquidacion de IVA; no son saldo bancario ni declaracion tributaria.']})
    return report
