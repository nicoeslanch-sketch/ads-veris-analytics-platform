import { describe, expect, it } from 'vitest'
import { compactPeriodLabel, periodSelectValue } from './periodPresentation'

describe('period presentation', () => {
  it('does not label a complete or partial year as January', () => {
    for (const to of ['2026-12-31', '2026-09-30']) {
      const period = { from: '2026-01-01', to, label: '2026' }
      expect(periodSelectValue(period)).toBe('2026')
      expect(compactPeriodLabel(period)).toBe('2026')
    }
  })
  it('keeps quarter and arbitrary ranges distinct from a month', () => {
    const quarter = { from: '2025-01-01', to: '2025-03-31', label: '2025-T1' }
    expect(periodSelectValue(quarter)).toBe('custom')
    expect(compactPeriodLabel(quarter)).toBe('2025-T1')
    const range = { from: '2025-01-03', to: '2025-01-20', label: 'Rango de fechas' }
    expect(periodSelectValue(range)).toBe('custom')
    expect(compactPeriodLabel(range)).toBe('Rango')
  })
  it('recognizes complete months including leap years and the unfiltered state', () => {
    expect(periodSelectValue({ from: '2024-02-01', to: '2024-02-29', label: 'Febrero' })).toBe('2024-02')
    expect(periodSelectValue({ from: '2024-02-01', to: '2024-02-28', label: 'Febrero' })).toBe('custom')
    expect(periodSelectValue({ from: null, to: null, label: 'Todo' })).toBe('all')
    expect(compactPeriodLabel({ from: null, to: null, label: 'Todo' })).toBe('Todo')
  })
})
