import { afterEach, describe, expect, it, vi } from 'vitest'
import demo from '../demo/data/demo_metrics.json'
import type { MetricsResult } from './types'
import { buildReportCsv, openPrintableReport } from './report'
import { getActiveCurrency, setActiveCurrency } from './format'

function metrics(currency = 'UF'): MetricsResult {
  const result = structuredClone(demo) as unknown as MetricsResult
  result.moneda = currency
  result.kpis.ingresos_totales = { valor: 0.004, variacion_pct: null }
  result.evolucion_mensual = [{ mes: '2026-01', ingresos: 0.004, gastos: 0, utilidad: 0.004 }]
  return result
}

function printable(result: MetricsResult, company = 'Empresa de prueba') {
  const popup = {
    document: { open: vi.fn(), write: vi.fn(), close: vi.fn() },
    addEventListener: vi.fn(), setTimeout: vi.fn(), print: vi.fn(), opener: {},
  }
  vi.stubGlobal('window', { open: vi.fn(() => popup) })
  openPrintableReport(result, company)
  return { html: String(popup.document.write.mock.calls[0][0]), popup }
}

afterEach(() => { vi.unstubAllGlobals(); setActiveCurrency('CLP') })

describe('report currency and export integrity', () => {
  it('labels UF and preserves fractional values in CSV without changing session currency', () => {
    setActiveCurrency('USD')
    const csv = buildReportCsv(metrics())
    expect(csv).toContain('INDICADORES (UF)')
    expect(csv).not.toContain('(CLP)')
    expect(csv).toContain('Ingresos totales;0,004;')
    expect(csv).toContain('2026-01;0,004;0;0,004')
    expect(getActiveCurrency()).toBe('USD')
  })

  it('uses the report currency and precision in print, independent of session currency', () => {
    setActiveCurrency('USD')
    expect(printable(metrics()).html).toContain('UF 0,004')
    expect(getActiveCurrency()).toBe('USD')
    const usd = metrics('USD')
    usd.kpis.ingresos_totales!.valor = 12.34
    expect(printable(usd).html).toContain('US$12,34')
  })

  it('does not publish nonfinite values in CSV or print', () => {
    const result = metrics('CLP')
    result.kpis.ingresos_totales!.valor = Infinity
    result.kpis.ticket_promedio = NaN
    expect(buildReportCsv(result)).not.toMatch(/Infinity|NaN/)
    expect(printable(result).html).not.toMatch(/Infinity|NaN|\u221e/)
  })

  it('escapes hostile labels and tiny UF bounds without inline scripts', () => {
    const result = metrics()
    result.archivo = '<script>alert(1)</script>.xlsx'
    result.por_categoria![0].nombre = '<img src=x onerror=alert(1)>'
    result.kpis.ingresos_totales!.valor = 1e-9
    const { html, popup } = printable(result, '<svg onload=alert(1)>')
    expect(html).not.toMatch(/<script|<img|<svg/)
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(html).toContain('&lt;UF 0,00000001')
    expect(popup.opener).toBeNull()
    expect(popup.addEventListener).toHaveBeenCalledWith('load', expect.any(Function), { once: true })
    popup.addEventListener.mock.calls[0][1]()
    popup.setTimeout.mock.calls[0][0]()
    expect(popup.print).toHaveBeenCalledOnce()
  })

  it('keeps a missing currency in CLP even when the session was UF', () => {
    setActiveCurrency('UF')
    const result = metrics('')
    expect(buildReportCsv(result)).toContain('INDICADORES (CLP)')
    expect(printable(result).html).toContain('Moneda: CLP')
    expect(getActiveCurrency()).toBe('UF')
  })
})
