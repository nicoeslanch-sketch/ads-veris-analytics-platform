import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CatalogRelationship, RelationshipDashboard } from './types'
vi.mock('./api', () => ({ apiPost: vi.fn(), apiPostJob: vi.fn(), buildDatasetForm: () => new FormData() }))
vi.mock('./sessionAnalysisCache', () => ({ clearSessionAnalysis: vi.fn(), readSessionAnalysis: () => null, writeSessionAnalysis: vi.fn() }))
import { apiPostJob } from './api'
import { clearRelationshipDashboardCaches, fetchRelationshipDashboard } from './relationshipDashboard'

const params = { file: null, storagePath: 'owner/test.csv', datasetId: 'dataset', manifest: { hojas: [] } }
const relation = { id: 'r', left_sheet: 'Ventas', right_sheet: 'Productos', left_keys: ['ID'], right_keys: ['ID'] } as CatalogRelationship

describe('Relationship job consumers', () => {
  beforeEach(() => { vi.useRealTimers(); clearRelationshipDashboardCaches(); vi.clearAllMocks() })
  it('shares a calculation and cancels only after every consumer leaves', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | undefined
    vi.mocked(apiPostJob).mockImplementation((_path, _form, options) => {
      signal = options?.signal
      return new Promise(() => {})
    })
    const one = new AbortController(), two = new AbortController()
    void fetchRelationshipDashboard(params, relation, { from: null, to: null }, one.signal)
    void fetchRelationshipDashboard(params, relation, { from: null, to: null }, two.signal)
    expect(apiPostJob).toHaveBeenCalledTimes(1)
    one.abort(); await vi.advanceTimersByTimeAsync(300)
    expect(signal?.aborted).toBe(false)
    two.abort(); await vi.advanceTimersByTimeAsync(300)
    expect(signal?.aborted).toBe(true)
  })
  it('uses durable admission and reuses completed results', async () => {
    vi.mocked(apiPostJob).mockResolvedValue({ available: true } as RelationshipDashboard)
    await fetchRelationshipDashboard(params, relation, { from: null, to: null })
    await fetchRelationshipDashboard(params, relation, { from: null, to: null })
    expect(apiPostJob).toHaveBeenCalledTimes(1)
    expect(vi.mocked(apiPostJob).mock.calls[0][0]).toBe('/analysis/jobs/relationship-dashboard')
  })
})
