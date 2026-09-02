import { describe, expect, it } from 'vitest'
import { hasAssistantMetricFilters } from './AiPanel'

describe('hasAssistantMetricFilters', () => {
  it('reuses the global snapshot only for the unfiltered dashboard', () => {
    expect(hasAssistantMetricFilters({ from: null, to: null }, {})).toBe(false)
  })

  it('requires visible metrics for dates or business filters', () => {
    expect(hasAssistantMetricFilters({ from: '2026-05-01', to: '2026-05-31' }, {})).toBe(true)
    expect(hasAssistantMetricFilters({ from: null, to: null }, { equipo: 'FLUJO' })).toBe(true)
  })
})
