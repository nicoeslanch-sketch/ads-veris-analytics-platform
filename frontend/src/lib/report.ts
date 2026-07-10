/** Generación de reportes (Fase 5, MVP) — sin dependencias nuevas.

- Excel: CSV con separador ';' y BOM UTF-8 (abre correcto en Excel es-CL).
- PDF: ventana imprimible con estilos de marca → "Guardar como PDF".
*/

import type { MetricsResult } from './types'

function csvNumber(value: number | null | undefined): string {
  if (value == null) return ''
  // es-CL: coma decimal, sin separador de miles (Excel lo interpreta como número)
  return String(Math.round(value * 100) / 100).replace('.', ',')
}

function csvCell(value: string): string {
  // Neutraliza formula injection: Excel interpreta =, +, -, @ al inicio como fórmula
  const safe = /^[=+\-@]/.test(value) ? `'${value}` : value
  return /[;"\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
}

/** Arma el CSV completo del reporte (todas las secciones del dashboard). */
export function buildReportCsv(m: MetricsResult): string {
  const lines: string[] = []
  const push = (...cells: Array<string | number | null | undefined>) => {
    lines.push(
      cells
        .map((c) => (typeof c === 'number' ? csvNumber(c) : csvCell(String(c ?? ''))))
        .join(';'),
    )
  }

  push('Reporte ADS Veris')
  push('Archivo', m.archivo)
  push('Periodo', `${m.periodo.desde ?? 'inicio'} a ${m.periodo.hasta ?? 'fin'}`)
  push('Calidad de datos (%)', m.calidad_datos)
  push()

  push('INDICADORES (CLP)')
  push('Indicador', 'Valor', 'Variación %')
  push('Ingresos totales', m.kpis.ingresos_totales.valor, m.kpis.ingresos_totales.variacion_pct)
  if (m.kpis.gastos_totales) push('Gastos totales', m.kpis.gastos_totales.valor, m.kpis.gastos_totales.variacion_pct)
  if (m.kpis.ganancia_neta) push('Utilidad bruta', m.kpis.ganancia_neta.valor, m.kpis.ganancia_neta.variacion_pct)
  if (m.kpis.margen_utilidad_pct) push('Margen de utilidad (%)', m.kpis.margen_utilidad_pct.valor)
  if (m.kpis.flujo_caja) push('Flujo de caja operacional', m.kpis.flujo_caja.valor, m.kpis.flujo_caja.variacion_pct)
  push('Transacciones', m.kpis.transacciones)
  push('Ticket promedio', m.kpis.ticket_promedio)
  push()

  if (m.evolucion_mensual.length > 0) {
    push('EVOLUCIÓN MENSUAL (CLP)')
    push('Mes', 'Ingresos', 'Gastos', 'Utilidad')
    for (const row of m.evolucion_mensual) push(row.mes, row.ingresos, row.gastos, row.utilidad)
    push()
  }

  const sections: Array<[string, MetricsResult['por_categoria']]> = [
    ['POR CATEGORÍA', m.por_categoria],
    ['POR CANAL / SUCURSAL', m.ventas_por_canal],
    ['TOP PRODUCTOS / SERVICIOS', m.top_productos],
  ]
  for (const [title, rows] of sections) {
    if (!rows?.length) continue
    push(title)
    push('Nombre', 'Ingresos (CLP)', '% del total', 'Utilidad (CLP)', 'Margen %')
    for (const row of rows) push(row.nombre, row.ingresos, row.porcentaje, row.utilidad, row.margen_pct)
    push()
  }

  if (m.proyeccion) {
    push('PROYECCIÓN (PRÓXIMOS 3 MESES, CLP)')
    push('Mes', 'Ingresos estimados')
    for (const row of m.proyeccion.meses) push(row.mes, row.ingresos)
  }

  return lines.join('\r\n')
}

/** Descarga el CSV con BOM (Excel es-CL lo abre con acentos y ; correctos). */
export function downloadReportCsv(m: MetricsResult): void {
  const blob = new Blob(['﻿' + buildReportCsv(m)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `reporte-ads-veris-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

// ── Reporte imprimible (PDF vía diálogo del navegador) ───────────────────────

const clp = (v: number | null | undefined) =>
  v == null ? '—' : `$${new Intl.NumberFormat('es-CL').format(Math.round(v))}`
const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toLocaleString('es-CL', { maximumFractionDigits: 1 })}%`

/** Todo valor que venga de los datos del usuario se escapa antes de entrar al HTML. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function tableHtml(
  headers: string[],
  rows: Array<Array<string>>,
): string {
  return `<table>
    <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>
  </table>`
}

export function openPrintableReport(m: MetricsResult, empresa: string | null): void {
  const kpiRows: Array<[string, string]> = [
    ['Ingresos totales', clp(m.kpis.ingresos_totales.valor)],
    ...(m.kpis.gastos_totales ? [['Gastos totales', clp(m.kpis.gastos_totales.valor)] as [string, string]] : []),
    ...(m.kpis.ganancia_neta ? [['Utilidad bruta', clp(m.kpis.ganancia_neta.valor)] as [string, string]] : []),
    ...(m.kpis.margen_utilidad_pct
      ? [['Margen de utilidad', pct(m.kpis.margen_utilidad_pct.valor)] as [string, string]]
      : []),
    ['Transacciones', new Intl.NumberFormat('es-CL').format(m.kpis.transacciones)],
    ['Ticket promedio', clp(m.kpis.ticket_promedio)],
  ]

  const groupSection = (title: string, rows: MetricsResult['por_categoria']) =>
    rows?.length
      ? `<h2>${title}</h2>` +
        tableHtml(
          ['Nombre', 'Ingresos', '% del total', 'Utilidad', 'Margen'],
          rows.map((r) => [r.nombre, clp(r.ingresos), pct(r.porcentaje), clp(r.utilidad), pct(r.margen_pct)]),
        )
      : ''

  const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Reporte ADS Veris — ${escapeHtml(m.archivo)}</title>
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font-family: 'Poppins', 'Segoe UI', sans-serif; color: #1a3a52; padding: 32px; font-size: 13px; }
  header { border-bottom: 3px solid #00a8a8; padding-bottom: 12px; margin-bottom: 20px;
           display: flex; justify-content: space-between; align-items: baseline; }
  .brand { font-size: 22px; font-weight: 700; }
  .brand span { color: #d4af37; }
  .meta { color: #5c7285; font-size: 12px; text-align: right; }
  h2 { font-size: 15px; margin: 22px 0 8px; color: #12283a; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
       color: #5c7285; border-bottom: 1px solid #d8e0e6; padding: 6px 8px; }
  td { padding: 6px 8px; border-bottom: 1px solid #eef2f5; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .kpi { border: 1px solid #d8e0e6; border-radius: 10px; padding: 10px 12px; }
  .kpi .label { font-size: 11px; color: #5c7285; text-transform: uppercase; letter-spacing: .04em; }
  .kpi .value { font-size: 17px; font-weight: 700; margin-top: 2px; }
  footer { margin-top: 28px; padding-top: 10px; border-top: 1px solid #d8e0e6;
           color: #5c7285; font-size: 11px; }
  @media print { body { padding: 0; } }
</style>
</head>
<body>
<header>
  <div class="brand">ADS <span>Veris</span></div>
  <div class="meta">
    ${empresa ? `<div><strong>${escapeHtml(empresa)}</strong></div>` : ''}
    <div>Archivo: ${escapeHtml(m.archivo)}</div>
    <div>Periodo: ${escapeHtml(m.periodo.desde ?? 'inicio')} — ${escapeHtml(m.periodo.hasta ?? 'fin')}</div>
    <div>Generado: ${new Date().toLocaleDateString('es-CL', { day: '2-digit', month: 'long', year: 'numeric' })}</div>
  </div>
</header>

<h2>Indicadores del periodo</h2>
<div class="kpis">
  ${kpiRows.map(([label, value]) => `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`).join('')}
</div>

${
  m.evolucion_mensual.length
    ? '<h2>Evolución mensual</h2>' +
      tableHtml(
        ['Mes', 'Ingresos', 'Gastos', 'Utilidad'],
        m.evolucion_mensual.map((r) => [r.mes, clp(r.ingresos), clp(r.gastos), clp(r.utilidad)]),
      )
    : ''
}
${groupSection('Análisis por categoría', m.por_categoria)}
${groupSection('Ventas por canal / sucursal', m.ventas_por_canal)}
${groupSection('Top productos / servicios', m.top_productos)}
${
  m.proyeccion
    ? '<h2>Proyección (próximos 3 meses)</h2>' +
      tableHtml(['Mes', 'Ingresos estimados'], m.proyeccion.meses.map((r) => [r.mes, clp(r.ingresos)]))
    : ''
}

<footer>
  Generado por ADS Veris — plataforma de análisis de datos para PyMEs.
  Calidad de datos del archivo: ${pct(m.calidad_datos)}.
</footer>
<script>window.onload = () => setTimeout(() => window.print(), 300)</script>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) return
  win.document.write(html)
  win.document.close()
}
