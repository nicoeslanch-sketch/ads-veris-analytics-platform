import { describe, expect, it } from 'vitest'
import { relationshipBotContext } from './relationshipBotContext'
import type { RelationshipDashboard } from './types'

describe('relationship bot payload', () => {
  it('retains only bounded published chart values, not entire table rows', () => {
    const dashboard = {
      relation: { label: 'Ventas + Productos' }, currency: 'UF', available: true,
      period: { desde: '2026-01-01', hasta: '2026-02-01' },
      kpis: [], findings: [], alerts: [], table: { rows: [{ email: 'private@example.invalid' }] },
      charts: [{ title: 'Ventas por producto', category_key: 'name',
        series: [{ key: 'ventas', label: 'Ventas', format: 'currency' }],
        data: Array.from({ length: 50 }, () => ({ name: 'A', ventas: 125.75, private_field: 'hidden' })) }],
    } as unknown as RelationshipDashboard
    const context = relationshipBotContext(dashboard)!
    expect(context.charts[0].data).toHaveLength(30)
    expect(context.charts[0].data[0]).toEqual({ name: 'A', ventas: 125.75 })
    expect(JSON.stringify(context)).not.toContain('private')
    expect(context.period.desde).toBe('2026-01-01')
    expect(relationshipBotContext(null)).toBeNull()
  })
})
