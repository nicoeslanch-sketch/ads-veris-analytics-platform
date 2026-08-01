import { describe, expect, it } from 'vitest'
import { canActivateResult, consolidationModeVisible, TERMINAL_RUN_STATUSES, upsertSource } from './state'
import { CONSOLIDATION_STEPS } from './GeneralConsolidationWizard'

describe('consolidation gating and state', () => {
  it('uses exactly the four user-facing steps', () => {
    expect(CONSOLIDATION_STEPS).toEqual(['Cargar', 'Revisar', 'Comprobar', 'Obtener resultado'])
  })
  it('stays hidden unless both flag and admin are true', () => {
    expect(consolidationModeVisible(false, true)).toBe(false)
    expect(consolidationModeVisible(true, false)).toBe(false)
    expect(consolidationModeVisible(true, true)).toBe(true)
  })

  it('replaces a role without duplicating it', () => {
    const result = upsertSource(
      [{ role: 'matricula', dataset_id: 'old', required: true }],
      'matricula',
      'new',
      true,
    )
    expect(result).toEqual([{ role: 'matricula', dataset_id: 'new', required: true }])
  })

  it('allows explicit activation only for usable annual results', () => {
    expect(canActivateResult('partial', true)).toBe(true)
    expect(canActivateResult('failed', true)).toBe(false)
    expect(canActivateResult('certified', false)).toBe(false)
  })

  it('polling stops for final warning and failure states', () => {
    expect(TERMINAL_RUN_STATUSES.has('valid_with_warnings')).toBe(true)
    expect(TERMINAL_RUN_STATUSES.has('running')).toBe(false)
  })
})
